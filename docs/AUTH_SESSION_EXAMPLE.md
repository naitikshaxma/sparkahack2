# Auth + Persistent Session Example

## 1) Login

```http
POST /api/login
Content-Type: application/json

{
  "email": "user@example.com",
  "name": "Voice User"
}
```

Response payload shape:

```json
{
  "success": true,
  "data": {
    "access_token": "<jwt>",
    "token_type": "bearer",
    "user": {
      "id": 1,
      "name": "Voice User",
      "email": "user@example.com"
    }
  }
}
```

## 2) Call Existing Endpoint (unchanged schema)

```http
POST /api/process-text
Authorization: Bearer <jwt>
Content-Type: multipart/form-data
```

`session_id`, `response_text`, `validation_passed`, and all existing fields remain unchanged.

## 3) Inspect Current Auth User

```http
GET /api/me
Authorization: Bearer <jwt>
```

This endpoint demonstrates protected-route access with middleware-attached `request.state.user_id`.

## 4) Persistence Behavior

- Session state is stored in `sessions.state_json`.
- Session-user binding is stored in `sessions.user_id`.
- Conversation entries are stored in `conversation_history`.
- After server restart, calling with the same `session_id` restores state from PostgreSQL.
