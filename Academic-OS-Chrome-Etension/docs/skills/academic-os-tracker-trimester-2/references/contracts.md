# Contracts

## Configuration

- Academic OS origin: `https://bits-dsai-tracker.web.app`
- Backend: `https://academic-os-api.onrender.com`
- Lumen: `https://lumen.bitspilani-digital.edu.in`
- Sync routes: `/api/lumen/sync`, optional `/api/lumen/sync/batch`, `/api/lumen/status`, `/api/lumen/history`, `/api/lumen/manual`
- Auto-refresh: 15 minutes; cleanup: 60 minutes; batch size: 25; batch sync disabled by default.

## Background message types

Allowlisted types are `STORE_FIREBASE_TOKEN`, `FETCH_LUMEN_PROGRESS`, `LUMEN_DATA_CAPTURED`, `MANUAL_SYNC_REQUEST`, `GET_STATUS`, `GET_PROGRESS_CACHE`, `SET_AUTO_SYNC`, and `SIGN_OUT`. Unknown types return `UNKNOWN_MESSAGE_TYPE`.

Important payloads:

- `STORE_FIREBASE_TOKEN`: `{ token: string, user?: object, expiresIn?: number }`.
- `LUMEN_DATA_CAPTURED`: `{ normalized: { type: string, data: any }, capturedAt?: number }`.
- `SET_AUTO_SYNC`: `{ enabled: boolean }`.
- `PUSH_PROGRESS_TO_PAGE`: internal broadcast carrying `{ progress }`.

## Progress shape

```ts
type Progress = {
  student: { name: string, userId: string | null } | null,
  courses: Array<{
    orgUnitId: number,
    courseName: string,
    courseCode: string | null,
    grades: Array<{ title: string, pointsNumerator: number|null, pointsDenominator: number|null, percentage: number|null }>,
    moduleProgress: { completed: number, total: number },
    assignments: Array<{ title: string, dueDate: string|null, status: string }>,
    quizzes: Array<{ title: string, isActive: boolean|null }>,
    discussions: Array<{ title: string, postCount: number|null }>,
    announcements: Array<{ title: string, postedDate: string|null }>,
    fetchErrors: string[]
  }>,
  fetchedAt: string,
  errors: string[]
}
```

The Academic OS page uses `ACADEMIC_OS_EXTENSION_READY`, `ACADEMIC_OS_AUTH`, `ACADEMIC_OS_REQUEST_PROGRESS`, `ACADEMIC_OS_REQUEST_REFRESH`, and receives `ACADEMIC_OS_PROGRESS_DATA`.

## Storage keys

`academicos_firebase_token`, `academicos_firebase_token_expiry`, `academicos_user_info`, `academicos_last_sync`, `academicos_sync_queue`, `academicos_auto_sync_enabled`, `academicos_progress_cache`, `academicos_last_sync_status`, and `academicos_seen_message_ids`.

## Status values

`LAST_SYNC_STATUS` is normally `ok`, `auth_expired`, `backend_offline`, or `lumen_offline`. Auth status has separate `signedIn`, `expired`, and `expiringSoon` fields so UI can recover an expired session without pretending the user never signed in.
