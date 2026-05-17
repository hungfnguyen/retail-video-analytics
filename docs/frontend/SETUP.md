# Frontend Setup Guide

This guide explains how team members can clone the repository, install frontend dependencies, and run the React dashboard locally.

## Prerequisites

- Git
- Node.js 20 or newer
- npm

Check the installed versions:

```bash
node --version
npm --version
git --version
```

## Clone The Repository

```bash
git clone https://github.com/hungfnguyen/retail-video-analytics.git
cd retail-video-analytics
```

If the repository URL changes, use the project team's current Git remote URL.

## Install Frontend Dependencies

The frontend app is located in `frontend/`.

```bash
cd frontend
npm install
```

On Windows PowerShell, if `npm` is blocked by execution policy, use:

```powershell
npm.cmd install
```

## Start The Development Server

```bash
npm run dev
```

On Windows PowerShell:

```powershell
npm.cmd run dev
```

Vite will print the local URL, usually:

```text
http://localhost:5173
```

## Build For Production

```bash
npm run build
```

On Windows PowerShell:

```powershell
npm.cmd run build
```

The production build output is generated in `frontend/dist/`. This folder is ignored by Git and should not be committed.

## Project Structure

The frontend follows a feature-based structure:

```text
frontend/src/
├── app/
│   └── App.tsx
├── features/
│   └── live/
│       ├── api/
│       ├── components/
│       ├── hooks/
│       ├── mocks/
│       ├── LivePage.tsx
│       └── types.ts
└── shared/
    └── components/
```

Feature-specific code should stay inside `features/{feature-name}/`. Shared layout and reusable UI components should go under `shared/`.

## Mock Data Workflow

The Live page currently uses mock data:

```text
features/live/api/liveApi.ts
→ features/live/mocks/liveMock.ts
→ features/live/types.ts
```

When the FastAPI backend is available, update only the API layer first:

```text
features/live/api/liveApi.ts
```

Keep the UI components dependent on typed contracts instead of raw backend responses.

## Files That Should Not Be Committed

The following frontend artifacts are ignored by Git:

```text
frontend/node_modules/
frontend/dist/
frontend/dist-ssr/
frontend/.vite/
frontend/.cache/
*.local
```

Commit source files such as:

```text
frontend/package.json
frontend/package-lock.json
frontend/src/
frontend/vite.config.ts
frontend/tsconfig*.json
```
