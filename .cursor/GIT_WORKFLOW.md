# Git workflow: fixing "ahead 4, behind 2" (diverged branch)

Your `student-version` has **4 commits** only on your machine and **2 commits** only on `origin`. You need to integrate both.

---

## Option A: Merge (recommended when learning — keeps full history)

### Step 1: Make sure you're clean and on the right branch
```bash
git status                    # should say "nothing to commit, working tree clean"
git branch                    # * should be student-version
```

### Step 2: Fetch the latest from origin (no merge yet)
```bash
git fetch origin
```
This only updates your local copy of `origin/student-version`. Your branch does not change yet.

### Step 3: Pull = fetch + merge
```bash
git pull origin student-version
```
Git will:
- Merge `origin/student-version` into your current branch.
- If there are no conflicts, it creates a **merge commit** and you're done.
- If there are conflicts, Git will tell you which files; you fix them, then:
  ```bash
  git add <fixed-files>
  git commit -m "Merge origin/student-version"
  ```

### Step 4: Push your updated branch
```bash
git push origin student-version
```
Now remote has your 4 commits + the 2 it had + the merge commit. "Ahead/behind" goes to 0.

---

## Option B: Rebase (linear history, no merge commit)

Use this when you want a straight line of commits (your 4 replayed on top of the 2 from origin).

### Step 1–2: Same as above — fetch first
```bash
git fetch origin
```

### Step 3: Rebase your commits on top of origin
```bash
git rebase origin/student-version
```
Git will:
- Temporarily remove your 4 commits.
- Fast-forward to match the 2 commits on origin.
- Replay your 4 commits one by one on top.
- If there's a conflict on any commit, you fix it, then:
  ```bash
  git add <fixed-files>
  git rebase --continue
  ```
  (To abort and go back to before rebase: `git rebase --abort`)

### Step 4: Push (may need force because history changed)
```bash
git push origin student-version
```
If Git says "rejected (non-fast-forward)", use:
```bash
git push origin student-version --force-with-lease
```
`--force-with-lease` is safer than `--force`: it only overwrites the remote if nobody else pushed in the meantime.

---

## Quick reference

| Goal                         | Command |
|-----------------------------|---------|
| See ahead/behind            | `git status` or `git branch -vv` |
| Get remote updates only     | `git fetch origin` |
| Merge remote into current   | `git pull origin student-version` |
| Rebase on remote            | `git pull --rebase origin student-version` or `git rebase origin/student-version` |
| Send your commits to remote | `git push origin student-version` |
| Safe force push after rebase| `git push origin student-version --force-with-lease` |

---

## Summary for your situation

1. **Merge path:** `git fetch origin` → `git pull origin student-version` → fix conflicts if any → `git push origin student-version`.
2. **Rebase path:** `git fetch origin` → `git rebase origin/student-version` → fix conflicts if any → `git push origin student-version --force-with-lease`.

Use **merge** first to get comfortable; use **rebase** when you want a cleaner, linear history.
