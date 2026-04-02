# Mobile MVP – Required APIs

Minimal set of backend APIs needed for a **wardrobe mobile app MVP**: sign in, manage profile, add/view clothes, get outfit suggestions, and see today’s weather.

All endpoints are under base path **`/api/v1`**. Send **`Authorization: Bearer <access_token>`** on every request except auth and health.

---

## 1. Auth (required)

| Method | Path | Purpose |
|--------|------|--------|
| `GET`  | `/auth/status` | Check if auth is configured (e.g. before showing login). |
| `POST` | `/auth/sync`   | After app/OIDC login: sync user to backend and get **access_token**. |
| `GET`  | `/auth/session`| Validate token and get current user (optional; can use `/users/me` instead). |

**`POST /auth/sync` body:**
```json
{
  "external_id": "string",
  "email": "string",
  "display_name": "string",
  "avatar_url": "string | null",
  "id_token": "string | null"
}
```
**Response:** `id`, `email`, `display_name`, `is_new_user`, `onboarding_completed`, **`access_token`**.

---

## 2. User (required)

| Method | Path | Purpose |
|--------|------|--------|
| `GET`  | `/users/me` | Get current user profile (after login / for session check). |
| `PATCH`| `/users/me` | Update profile (display_name, timezone, location_*). |
| `POST` | `/users/me/onboarding/complete` | Mark onboarding done. |

---

## 3. Wardrobe items (required)

| Method | Path | Purpose |
|--------|------|--------|
| `GET`   | `/items` | List user’s items (paginated). |
| `POST`  | `/items` | Add one item (multipart: image + optional form fields). |
| `GET`   | `/items/{item_id}` | Get one item (details, images). |
| `PATCH` | `/items/{item_id}` | Update item (name, type, colors, etc.). |
| `DELETE`| `/items/{item_id}` | Delete item. |
| `GET`   | `/items/types` | List valid item types (for filters/forms). |
| `GET`   | `/items/colors` | List valid colors (for filters/forms). |

**`POST /items`:** `multipart/form-data`: `image` (file), optional: `type`, `subtype`, `name`, `brand`, `notes`, `colors` (comma-separated), `primary_color`, `favorite`.

**Image rules:** One image per request. Supported formats: **JPEG, PNG, WebP, HEIC**. Backend generates thumbnails and can queue AI tagging (type/colors) if you omit `type`.

---

## 3.1 Integrating: “Take a picture and add item”

No backend changes are required. You only need to capture a photo, then send it as multipart to `POST /items`.

### API contract (reminder)

- **URL:** `POST /api/v1/items`
- **Headers:** `Authorization: Bearer <access_token>`
- **Body:** `multipart/form-data`
  - **Required:** `image` — single image file (JPEG, PNG, WebP, or HEIC).
  - **Optional:** `type`, `subtype`, `name`, `brand`, `notes`, `colors` (comma-separated), `primary_color`, `favorite` (string `"true"` / `"false"`).
- **Response:** `201` + full item object (id, images, etc.). Duplicate image → `409`.

### Web (browser)

Use a file input with `capture` so mobile devices open the camera:

```html
<input
  type="file"
  accept="image/*"
  capture="environment"
  onChange={handleFileChange}
/>
```

Then build `FormData` and POST (do **not** set `Content-Type`; the browser sets it with the boundary):

```js
const formData = new FormData();
formData.append('image', file);           // required
formData.append('type', 'shirt');         // optional; omit to let AI detect

const response = await fetch(`${API_BASE}/api/v1/items`, {
  method: 'POST',
  headers: { Authorization: `Bearer ${accessToken}` },
  body: formData,
});
const item = await response.json();
```

The existing Next.js app does this in onboarding and add-item dialog (see `frontend/app/onboarding/page.tsx` and `frontend/lib/hooks/use-items.ts`).

### Mobile (React Native / Expo)

1. **Capture photo** with Expo ImagePicker or a native camera module.
2. **Get a file URI or blob** the app can send (e.g. `result.uri` from `launchCameraAsync`).
3. **Build multipart body** and POST with the access token.

**Expo (ImagePicker) example:**

```ts
import * as ImagePicker from 'expo-image-picker';

// Request camera permission once
const { status } = await ImagePicker.requestCameraPermissionsAsync();
if (status !== 'granted') return;

const result = await ImagePicker.launchCameraAsync({
  mediaTypes: ImagePicker.MediaTypeOptions.Images,
  allowsEditing: true,
  aspect: [1, 1],
  quality: 0.9,
});
if (result.canceled) return;

const uri = result.assets[0].uri;  // file:// or content://
```

**Build FormData and POST (React Native):**

In React Native you typically need the file as a blob or use a library that supports multipart from URI. Example with `uri` and `fetch` (works when the runtime supports file URIs in FormData, e.g. newer React Native / Expo):

```ts
const formData = new FormData();
// Append image: field name must be "image"
formData.append('image', {
  uri,
  name: 'photo.jpg',
  type: 'image/jpeg',
} as any);
formData.append('type', 'unknown');  // optional

const response = await fetch(`${API_BASE}/api/v1/items`, {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${accessToken}`,
    // Do NOT set Content-Type; FormData sets it with boundary
  },
  body: formData,
});
const item = await response.json();
```

If your environment doesn’t support appending `{ uri, name, type }` to FormData, use a small wrapper (e.g. `expo-file-system` readAsString base64 then blob, or a library like `react-native-blob-util` / `rn-fetch-blob`) to get a Blob/File and append that to FormData instead.

### Mobile (Flutter / native)

Same idea: open camera → get image file or bytes → build multipart request with:

- Part name: `image`, body: image file/bytes, content-type: `image/jpeg` (or png/webp/heic).
- Optional parts: `type`, `name`, `colors`, etc. as string fields.

Then `POST /api/v1/items` with `Authorization: Bearer <access_token>`.

### Flow summary

1. User taps “Add item” / “Take photo”.
2. App opens camera (or gallery if you allow).
3. User takes/selects one photo.
4. App builds `multipart/form-data` with `image` (+ optional fields).
5. `POST /api/v1/items` with Bearer token.
6. On 201: show success, refresh wardrobe list; on 409: show “Already in wardrobe”; on 4xx: show error.

---

## 4. Outfit suggestions (required)

| Method | Path | Purpose |
|--------|------|--------|
| `POST` | `/outfits/suggest` | Get one outfit suggestion. |
| `GET`  | `/outfits` | List past suggestions (history). |
| `GET`  | `/outfits/{outfit_id}` | Get one outfit details. |
| `POST` | `/outfits/{outfit_id}/accept` | Mark “wore it”. |
| `POST` | `/outfits/{outfit_id}/reject` | Dismiss suggestion. |

**`POST /outfits/suggest` body:**
```json
{
  "occasion": "casual",
  "weather_override": null,
  "exclude_items": [],
  "include_items": []
}
```
Use **weather** from `/weather/current` (or pass `weather_override`) for better suggestions.

---

## 5. Weather (required for good suggestions)

| Method | Path | Purpose |
|--------|------|--------|
| `GET` | `/weather/current` | Current weather (for outfit suggest). |

Requires user location (set in `/users/me`). Optional for MVP if you allow manual weather or skip weather.

---

## 6. Images (required to show clothes)

| Method | Path | Purpose |
|--------|------|--------|
| `GET` | `/images/{user_id}/{filename}` | Get item image (with `Authorization` or signed query params). |

Item responses include image URLs that point to this path; mobile app just loads them with the same Bearer token.

---

## 7. Health (recommended)

| Method | Path | Purpose |
|--------|------|--------|
| `GET` | `/health` or `/health/health` | Liveness; check backend is up. |

---

## Optional for MVP (simplify first release)

- **Preferences** `GET/PATCH /preferences` – AI model, etc. (server defaults are enough for MVP).
- **Outfit feedback** `POST /outfits/{id}/feedback` – ratings (can add later).
- **Item wear** `POST /items/{id}/wear` – “wore this today” (can derive from accept outfit).

---

## Post-MVP (skip for first app version)

- Families, pairings, notifications, schedules.
- Analytics, learning insights.
- Bulk upload/delete, wash tracking, item history, reorder images, etc.

---

## Summary checklist

| Area     | Endpoints |
|----------|-----------|
| Auth     | `GET /auth/status`, `POST /auth/sync` |
| User     | `GET /users/me`, `PATCH /users/me`, `POST /users/me/onboarding/complete` |
| Items    | `GET /items`, `POST /items`, `GET /items/{id}`, `PATCH /items/{id}`, `DELETE /items/{id}`, `GET /items/types`, `GET /items/colors` |
| Outfits  | `POST /outfits/suggest`, `GET /outfits`, `GET /outfits/{id}`, `POST /outfits/{id}/accept`, `POST /outfits/{id}/reject` |
| Weather  | `GET /weather/current` |
| Images   | `GET /images/{user_id}/{filename}` |
| Health   | `GET /health` |

Your existing backend already exposes these; the mobile app only needs to call them with the token from `POST /auth/sync` and use the same request/response shapes as the web app.
