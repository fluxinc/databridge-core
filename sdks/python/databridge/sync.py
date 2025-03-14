import base64
from io import BytesIO
import io
from PIL.Image import Image as PILImage
from PIL import Image
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, BinaryIO
from urllib.parse import urlparse

import jwt
from pydantic import BaseModel, Field
import requests

from .models import Document, ChunkResult, DocumentResult, CompletionResponse, IngestTextRequest, ChunkSource
from .rules import Rule

# Type alias for rules
RuleOrDict = Union[Rule, Dict[str, Any]]


class Cache:
    def __init__(self, db: "DataBridge", name: str):
        self._db = db
        self._name = name

    def update(self) -> bool:
        response = self._db._request("POST", f"cache/{self._name}/update")
        return response.get("success", False)

    def add_docs(self, docs: List[str]) -> bool:
        response = self._db._request("POST", f"cache/{self._name}/add_docs", {"docs": docs})
        return response.get("success", False)

    def query(
        self, query: str, max_tokens: Optional[int] = None, temperature: Optional[float] = None
    ) -> CompletionResponse:
        response = self._db._request(
            "POST",
            f"cache/{self._name}/query",
            params={"query": query, "max_tokens": max_tokens, "temperature": temperature},
            data="",
        )
        return CompletionResponse(**response)


class FinalChunkResult(BaseModel):
    content: str | PILImage = Field(..., description="Chunk content")
    score: float = Field(..., description="Relevance score")
    document_id: str = Field(..., description="Parent document ID")
    chunk_number: int = Field(..., description="Chunk sequence number")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Document metadata")
    content_type: str = Field(..., description="Content type")
    filename: Optional[str] = Field(None, description="Original filename")
    download_url: Optional[str] = Field(None, description="URL to download full document")

    class Config:
        arbitrary_types_allowed = True


class DataBridge:
    """
    DataBridge client for document operations.

    Args:
        uri (str, optional): DataBridge URI in format "databridge://<owner_id>:<token>@<host>".
            If not provided, connects to http://localhost:8000 without authentication.
        timeout (int, optional): Request timeout in seconds. Defaults to 30.
        is_local (bool, optional): Whether connecting to local development server. Defaults to False.

    Examples:
        ```python
        # Without authentication
        db = DataBridge()

        # With authentication
        db = DataBridge("databridge://owner_id:token@api.databridge.ai")
        ```
    """

    def __init__(self, uri: Optional[str] = None, timeout: int = 30, is_local: bool = False):
        self._timeout = timeout
        self._session = requests.Session()
        if is_local:
            self._session.verify = False  # Disable SSL for localhost
        self._is_local = is_local

        if uri:
            self._setup_auth(uri)
        else:
            self._base_url = "http://localhost:8000"
            self._auth_token = None

    def _setup_auth(self, uri: str) -> None:
        """Setup authentication from URI"""
        parsed = urlparse(uri)
        if not parsed.netloc:
            raise ValueError("Invalid URI format")

        # Split host and auth parts
        auth, host = parsed.netloc.split("@")
        _, self._auth_token = auth.split(":")

        # Set base URL
        self._base_url = f"{'http' if self._is_local else 'https'}://{host}"

        # Basic token validation
        jwt.decode(self._auth_token, options={"verify_signature": False})

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request"""
        headers = {}
        if self._auth_token:  # Only add auth header if we have a token
            headers["Authorization"] = f"Bearer {self._auth_token}"

        # Configure request data based on type
        if files:
            # Multipart form data for files
            request_data = {"files": files, "data": data}
            # Don't set Content-Type, let requests handle it
        else:
            # JSON for everything else
            headers["Content-Type"] = "application/json"
            request_data = {"json": data}

        response = self._session.request(
            method,
            f"{self._base_url}/{endpoint.lstrip('/')}",
            headers=headers,
            timeout=self._timeout,
            params=params,
            **request_data,
        )
        response.raise_for_status()
        return response.json()

    def _convert_rule(self, rule: RuleOrDict) -> Dict[str, Any]:
        """Convert a rule to a dictionary format"""
        if hasattr(rule, "to_dict"):
            return rule.to_dict()
        return rule

    def ingest_text(
        self,
        content: str,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        rules: Optional[List[RuleOrDict]] = None,
        use_colpali: bool = True,
    ) -> Document:
        """
        Ingest a text document into DataBridge.

        Args:
            content: Text content to ingest
            metadata: Optional metadata dictionary
            rules: Optional list of rules to apply during ingestion. Can be:
                  - MetadataExtractionRule: Extract metadata using a schema
                  - NaturalLanguageRule: Transform content using natural language
            use_colpali: Whether to use ColPali-style embedding model to ingest the text (slower, but significantly better retrieval accuracy for text and images)
        Returns:
            Document: Metadata of the ingested document

        Example:
            ```python
            from databridge.rules import MetadataExtractionRule, NaturalLanguageRule
            from pydantic import BaseModel

            class DocumentInfo(BaseModel):
                title: str
                author: str
                date: str

            doc = db.ingest_text(
                "Machine learning is fascinating...",
                metadata={"category": "tech"},
                rules=[
                    # Extract metadata using schema
                    MetadataExtractionRule(schema=DocumentInfo),
                    # Transform content
                    NaturalLanguageRule(prompt="Shorten the content, use keywords")
                ]
            )
            ```
        """
        request = IngestTextRequest(
            content=content,
            filename=filename,
            metadata=metadata or {},
            rules=[self._convert_rule(r) for r in (rules or [])],
            use_colpali=use_colpali,
        )
        response = self._request("POST", "ingest/text", data=request.model_dump())
        return Document(**response)

    def ingest_file(
        self,
        file: Union[str, bytes, BinaryIO, Path],
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        rules: Optional[List[RuleOrDict]] = None,
        use_colpali: bool = True,
    ) -> Document:
        """
        Ingest a file document into DataBridge.

        Args:
            file: File to ingest (path string, bytes, file object, or Path)
            filename: Name of the file
            metadata: Optional metadata dictionary
            rules: Optional list of rules to apply during ingestion. Can be:
                  - MetadataExtractionRule: Extract metadata using a schema
                  - NaturalLanguageRule: Transform content using natural language
            use_colpali: Whether to use ColPali-style embedding model to ingest the file (slower, but significantly better retrieval accuracy for images)

        Returns:
            Document: Metadata of the ingested document

        Example:
            ```python
            from databridge.rules import MetadataExtractionRule, NaturalLanguageRule
            from pydantic import BaseModel

            class DocumentInfo(BaseModel):
                title: str
                author: str
                department: str

            doc = db.ingest_file(
                "document.pdf",
                filename="document.pdf",
                metadata={"category": "research"},
                rules=[
                    MetadataExtractionRule(schema=DocumentInfo),
                    NaturalLanguageRule(prompt="Extract key points only")
                ], # Optional
                use_colpali=True, # Optional
            )
            ```
        """
        # Handle different file input types
        if isinstance(file, (str, Path)):
            file_path = Path(file)
            if not file_path.exists():
                raise ValueError(f"File not found: {file}")
            filename = file_path.name if filename is None else filename
            with open(file_path, "rb") as f:
                content = f.read()
                file_obj = BytesIO(content)
        elif isinstance(file, bytes):
            if filename is None:
                raise ValueError("filename is required when ingesting bytes")
            file_obj = BytesIO(file)
        else:
            if filename is None:
                raise ValueError("filename is required when ingesting file object")
            file_obj = file

        try:
            # Prepare multipart form data
            files = {"file": (filename, file_obj)}

            # Add metadata and rules
            form_data = {
                "metadata": json.dumps(metadata or {}),
                "rules": json.dumps([self._convert_rule(r) for r in (rules or [])]),
            }

            response = self._request(
                "POST", f"ingest/file?use_colpali={use_colpali}", data=form_data, files=files
            )
            return Document(**response)
        finally:
            # Close file if we opened it
            if isinstance(file, (str, Path)):
                file_obj.close()

    def retrieve_chunks(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        k: int = 4,
        min_score: float = 0.0,
        use_colpali: bool = True,
    ) -> List[FinalChunkResult]:
        """
        Retrieve relevant chunks.

        Args:
            query: Search query text
            filters: Optional metadata filters
            k: Number of results (default: 4)
            min_score: Minimum similarity threshold (default: 0.0)
            use_colpali: Whether to use ColPali-style embedding model to retrieve the chunks (only works for documents ingested with `use_colpali=True`)
        Returns:
            List[ChunkResult]

        Example:
            ```python
            chunks = db.retrieve_chunks(
                "What are the key findings?",
                filters={"department": "research"}
            )
            ```
        """
        request = {
            "query": query,
            "filters": filters,
            "k": k,
            "min_score": min_score,
            "use_colpali": json.dumps(use_colpali),
        }

        response = self._request("POST", "retrieve/chunks", request)
        chunks = [ChunkResult(**r) for r in response]

        final_chunks = []

        for chunk in chunks:
            if chunk.metadata.get("is_image"):
                try:
                    # Handle data URI format "data:image/png;base64,..."
                    content = chunk.content
                    if content.startswith("data:"):
                        # Extract the base64 part after the comma
                        content = content.split(",", 1)[1]

                    # Now decode the base64 string
                    image_bytes = base64.b64decode(content)
                    content = Image.open(io.BytesIO(image_bytes))
                except Exception as e:
                    print(f"Error processing image: {str(e)}")
                    # Fall back to using the content as text
                    print(chunk.content)
            else:
                content = chunk.content

            final_chunks.append(
                FinalChunkResult(
                    content=content,
                    score=chunk.score,
                    document_id=chunk.document_id,
                    chunk_number=chunk.chunk_number,
                    metadata=chunk.metadata,
                    content_type=chunk.content_type,
                    filename=chunk.filename,
                    download_url=chunk.download_url,
                )
            )

        return final_chunks

    def retrieve_docs(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        k: int = 4,
        min_score: float = 0.0,
        use_colpali: bool = True,
    ) -> List[DocumentResult]:
        """
        Retrieve relevant documents.

        Args:
            query: Search query text
            filters: Optional metadata filters
            k: Number of results (default: 4)
            min_score: Minimum similarity threshold (default: 0.0)
            use_colpali: Whether to use ColPali-style embedding model to retrieve the documents (only works for documents ingested with `use_colpali=True`)
        Returns:
            List[DocumentResult]

        Example:
            ```python
            docs = db.retrieve_docs(
                "machine learning",
                k=5
            )
            ```
        """
        request = {
            "query": query,
            "filters": filters,
            "k": k,
            "min_score": min_score,
            "use_colpali": json.dumps(use_colpali),
        }

        response = self._request("POST", "retrieve/docs", request)
        return [DocumentResult(**r) for r in response]

    def query(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        k: int = 4,
        min_score: float = 0.0,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        use_colpali: bool = True,
    ) -> CompletionResponse:
        """
        Generate completion using relevant chunks as context.

        Args:
            query: Query text
            filters: Optional metadata filters
            k: Number of chunks to use as context (default: 4)
            min_score: Minimum similarity threshold (default: 0.0)
            max_tokens: Maximum tokens in completion
            temperature: Model temperature
            use_colpali: Whether to use ColPali-style embedding model to generate the completion (only works for documents ingested with `use_colpali=True`)
        Returns:
            CompletionResponse

        Example:
            ```python
            response = db.query(
                "What are the key findings about customer satisfaction?",
                filters={"department": "research"},
                temperature=0.7
            )
            print(response.completion)
            ```
        """
        request = {
            "query": query,
            "filters": filters,
            "k": k,
            "min_score": min_score,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "use_colpali": json.dumps(use_colpali),
        }

        response = self._request("POST", "query", request)
        return CompletionResponse(**response)

    def list_documents(
        self, skip: int = 0, limit: int = 100, filters: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        List accessible documents.

        Args:
            skip: Number of documents to skip
            limit: Maximum number of documents to return
            filters: Optional filters

        Returns:
            List[Document]: List of accessible documents

        Example:
            ```python
            # Get first page
            docs = db.list_documents(limit=10)

            # Get next page
            next_page = db.list_documents(skip=10, limit=10, filters={"department": "research"})
            ```
        """
        response = self._request("GET", f"documents?skip={skip}&limit={limit}&filters={filters}")
        return [Document(**doc) for doc in response]

    def get_document(self, document_id: str) -> Document:
        """
        Get document metadata by ID.

        Args:
            document_id: ID of the document

        Returns:
            Document: Document metadata

        Example:
            ```python
            doc = db.get_document("doc_123")
            print(f"Title: {doc.metadata.get('title')}")
            ```
        """
        response = self._request("GET", f"documents/{document_id}")
        return Document(**response)
        
    def batch_get_documents(self, document_ids: List[str]) -> List[Document]:
        """
        Retrieve multiple documents by their IDs in a single batch operation.
        
        Args:
            document_ids: List of document IDs to retrieve
            
        Returns:
            List[Document]: List of document metadata for found documents
            
        Example:
            ```python
            docs = db.batch_get_documents(["doc_123", "doc_456", "doc_789"])
            for doc in docs:
                print(f"Document {doc.external_id}: {doc.metadata.get('title')}")
            ```
        """
        response = self._request("POST", "batch/documents", data=document_ids)
        return [Document(**doc) for doc in response]
        
    def batch_get_chunks(self, sources: List[Union[ChunkSource, Dict[str, Any]]]) -> List[FinalChunkResult]:
        """
        Retrieve specific chunks by their document ID and chunk number in a single batch operation.
        
        Args:
            sources: List of ChunkSource objects or dictionaries with document_id and chunk_number
            
        Returns:
            List[FinalChunkResult]: List of chunk results
            
        Example:
            ```python
            # Using dictionaries
            sources = [
                {"document_id": "doc_123", "chunk_number": 0},
                {"document_id": "doc_456", "chunk_number": 2}
            ]
            
            # Or using ChunkSource objects
            from databridge.models import ChunkSource
            sources = [
                ChunkSource(document_id="doc_123", chunk_number=0),
                ChunkSource(document_id="doc_456", chunk_number=2)
            ]
            
            chunks = db.batch_get_chunks(sources)
            for chunk in chunks:
                print(f"Chunk from {chunk.document_id}, number {chunk.chunk_number}: {chunk.content[:50]}...")
            ```
        """
        # Convert to list of dictionaries if needed
        source_dicts = []
        for source in sources:
            if isinstance(source, dict):
                source_dicts.append(source)
            else:
                source_dicts.append(source.model_dump())
                
        response = self._request("POST", "batch/chunks", data=source_dicts)
        chunks = [ChunkResult(**r) for r in response]
        
        final_chunks = []
        for chunk in chunks:
            if chunk.metadata.get("is_image"):
                try:
                    # Handle data URI format "data:image/png;base64,..."
                    content = chunk.content
                    if content.startswith("data:"):
                        # Extract the base64 part after the comma
                        content = content.split(",", 1)[1]

                    # Now decode the base64 string
                    image_bytes = base64.b64decode(content)
                    content = Image.open(io.BytesIO(image_bytes))
                except Exception as e:
                    print(f"Error processing image: {str(e)}")
                    # Fall back to using the content as text
                    content = chunk.content
            else:
                content = chunk.content

            final_chunks.append(
                FinalChunkResult(
                    content=content,
                    score=chunk.score,
                    document_id=chunk.document_id,
                    chunk_number=chunk.chunk_number,
                    metadata=chunk.metadata,
                    content_type=chunk.content_type,
                    filename=chunk.filename,
                    download_url=chunk.download_url,
                )
            )
            
        return final_chunks

    def create_cache(
        self,
        name: str,
        model: str,
        gguf_file: str,
        filters: Optional[Dict[str, Any]] = None,
        docs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new cache with specified configuration.

        Args:
            name: Name of the cache to create
            model: Name of the model to use (e.g. "llama2")
            gguf_file: Name of the GGUF file to use for the model
            filters: Optional metadata filters to determine which documents to include. These filters will be applied in addition to any specific docs provided.
            docs: Optional list of specific document IDs to include. These docs will be included in addition to any documents matching the filters.

        Returns:
            Dict[str, Any]: Created cache configuration

        Example:
            ```python
            # This will include both:
            # 1. Any documents with category="programming"
            # 2. The specific documents "doc1" and "doc2" (regardless of their category)
            cache = db.create_cache(
                name="programming_cache",
                model="llama2",
                gguf_file="llama-2-7b-chat.Q4_K_M.gguf",
                filters={"category": "programming"},
                docs=["doc1", "doc2"]
            )
            ```
        """
        # Build query parameters for name, model and gguf_file
        params = {"name": name, "model": model, "gguf_file": gguf_file}

        # Build request body for filters and docs
        request = {"filters": filters, "docs": docs}

        response = self._request("POST", "cache/create", request, params=params)
        return response

    def get_cache(self, name: str) -> Cache:
        """
        Get a cache by name.

        Args:
            name: Name of the cache to retrieve

        Returns:
            cache: A cache object that is used to interact with the cache.

        Example:
            ```python
            cache = db.get_cache("programming_cache")
            ```
        """
        response = self._request("GET", f"cache/{name}")
        if response.get("exists", False):
            return Cache(self, name)
        raise ValueError(f"Cache '{name}' not found")

    def close(self):
        """Close the HTTP session"""
        self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
