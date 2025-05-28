# Publishing the @morphik/ui Package

This document provides instructions for publishing the @morphik/ui package to npm.

## Prerequisites

1. You must have an npm account
2. You must be added as a contributor to the @morphik organization
3. You must be logged in to npm via the CLI (`npm login`)

## Publishing Steps

1. Ensure all changes are committed to the repository

2. Update the version in package.json (follow semantic versioning)

   ```bash
   npm version patch  # For bug fixes
   npm version minor  # For new features
   npm version major  # For breaking changes
   ```

3. Build the package

   ```bash
   npm run build:package
   ```

4. Pack it

   ```bash
   npm pack
   ```

5. Publish the package (or copy to clouds)

   ```bash
   npm publish --access public
   ```
