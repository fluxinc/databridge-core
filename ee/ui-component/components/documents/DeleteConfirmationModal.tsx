"use client";

import React from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface DeleteConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  itemName?: string; // Optional: name of the item being deleted for a more specific message
  itemCount?: number; // Optional: number of items for batch deletion
  loading?: boolean;
}

const DeleteConfirmationModal: React.FC<DeleteConfirmationModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  itemName,
  itemCount,
  loading = false,
}) => {
  let title = "Confirm Deletion";
  let description = "Are you sure you want to delete this item? This action cannot be undone.";

  if (itemCount && itemCount > 1) {
    title = `Confirm Deletion of ${itemCount} Items`;
    description = `Are you sure you want to delete these ${itemCount} items? This action cannot be undone.`;
  } else if (itemName) {
    title = `Confirm Deletion: ${itemName}`;
    description = `Are you sure you want to delete "${itemName}"? This action cannot be undone.`;
  }

  return (
    <Dialog open={isOpen} onOpenChange={open => !open && onClose()}>
      <DialogContent onPointerDownOutside={e => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button
            variant="destructive" // Changed to destructive for delete action
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? (itemCount && itemCount > 1 ? "Deleting Items..." : "Deleting Item...") : "Delete"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default DeleteConfirmationModal;
