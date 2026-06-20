# ReadingNotes

Reading notes for books, papers, and learning material (QTips, Python tricks, etc.).

## Sync local folders to GitHub

New folders on disk are **not** uploaded until you commit them:

```bash
cd ~/Documents/GitHub/ReadingNotes
git add -A
git commit -m "Add reading notes"
git push
```

Or run: `./scripts/sync_to_github.sh`

**Note:** Git does not track empty folders (e.g. an empty subfolder with no files).
