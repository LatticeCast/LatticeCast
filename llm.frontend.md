# LLM Context - Frontend

> **Note:** For general project context, see `llm.root.md`. For deployment, see `llm.deploy.md`.

## Tech Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| SvelteKit | 2.x | Full-stack framework |
| Svelte | 5.x | Reactive UI (runes) |
| Tailwind CSS | 4.x | Utility-first styling |
| TypeScript | 5.x | Type safety |
| Vite | 7.x | Build tool |
| Playwright | 1.55.x | Browser testing |
| Luxon | 3.x | Date/time utilities |

## Directory Structure

```
frontend/src/
├── routes/                  # SvelteKit pages
│   ├── +layout.svelte       # Global layout (sidebar nav, auth)
│   ├── +page.svelte         # Home (redirects to /login or /tables)
│   ├── login/+page.svelte   # OAuth login (Google, Authentik, simple ID)
│   ├── tables/+page.svelte  # Tables list + create
│   ├── tables/[id]/+page.svelte  # Table detail (grid, columns, rows)
│   ├── config/+page.svelte  # Settings (language, notifications)
│   ├── debug/+page.svelte   # Debug info (tokens, env)
│   └── callback/            # OAuth callbacks
│       ├── google/+page.svelte
│       └── authentik/+page.svelte
│
├── lib/
│   ├── auth/                # OAuth, PKCE
│   │   ├── auth.service.ts  # Login orchestration (startLogin, handleOAuthCallback)
│   │   ├── pkce.ts          # Code generation
│   │   └── providers/       # Provider configs (google.ts, authentik.ts, index.ts)
│   │
│   ├── stores/              # Svelte stores
│   │   ├── auth.store.ts    # Auth state (localStorage, 'loginInfo' key)
│   │   ├── settings.store.ts # Language, notification prefs
│   │   └── tables.store.ts  # Tables, columns, rows state + loading
│   │
│   ├── backend/             # API clients
│   │   ├── config.ts        # BACKEND_URL from VITE_BACKEND_URL
│   │   ├── auth.ts          # fetchAppConfig, exchangeCodeViaBackend, fetchMe
│   │   ├── tables.ts        # Tables/columns/rows CRUD API
│   │   └── storage.ts       # loadJson, saveJson (S3 storage)
│   │
│   ├── components/table/    # Table components
│   │   ├── TableGrid.svelte      # Main grid with inline editing
│   │   ├── TableHeader.svelte    # Column headers
│   │   ├── TableToolbar.svelte   # Search, sort, group, filter, export, import
│   │   ├── AddColumnModal.svelte # Add column modal
│   │   ├── RowExpandPanel.svelte # Row detail panel
│   │   ├── ImportTemplateModal.svelte  # Template import
│   │   ├── ImportPreviewModal.svelte   # CSV/JSON import preview
│   │   ├── ManageOptionsModal.svelte   # Select/tags options editor
│   │   ├── ContextMenu.svelte         # Right-click menu
│   │   └── table.utils.ts            # Column types, filters, grouping, CSV parsing
│   │
│   ├── types/               # TypeScript interfaces
│   │   ├── auth.ts          # AuthProvider, LoginInfo, UserInfo, OAuthProviderConfig
│   │   ├── table.ts         # Table, Column, Row, ColumnType, CRUD types
│   │   └── json.ts          # Json recursive type
│   │
│   └── UI/                  # Base components
│       ├── Button.svelte    # variant: primary, secondary, danger
│       ├── Input.svelte     # Styled text input
│       ├── Label.svelte     # Label wrapper
│       └── theme.svelte.ts  # Light/dark theme tokens, TAG_COLORS
│
├── app.css                  # Tailwind import
└── app.html                 # HTML template
```

## Svelte 5 Runes

```svelte
<script lang="ts">
  // Reactive state
  let count = $state(0);
  let items = $state<string[]>([]);

  // Derived values (computed)
  const doubled = $derived(count * 2);
  const itemCount = $derived(items.length);

  // Effects (side effects)
  $effect(() => {
    console.log('Count changed:', count);
    return () => console.log('Cleanup');
  });

  // Props
  let { title, onSubmit } = $props<{
    title: string;
    onSubmit: (value: string) => void;
  }>();
</script>
```

## Tailwind CSS 4

### Gradient Backgrounds
```svelte
<!-- Linear gradients (Tailwind v4 syntax) -->
<div class="bg-linear-to-br from-violet-500 via-purple-500 to-fuchsia-500">
<div class="bg-linear-to-r from-green-500 to-emerald-500">
```

### Common Patterns
```svelte
<!-- Card -->
<div class="rounded-3xl bg-white p-8 shadow-2xl">

<!-- Button -->
<button class="rounded-2xl bg-linear-to-r from-violet-500 to-fuchsia-500 px-4 py-4 font-semibold text-white transition hover:shadow-lg">

<!-- Input -->
<textarea class="w-full resize-none rounded-2xl border-2 border-gray-100 bg-gray-50 p-4 focus:border-purple-400 focus:outline-none">

<!-- Glassmorphism -->
<div class="bg-white/20 backdrop-blur-sm">
```

## Playwright Testing

### Setup
```bash
# Start browser container
docker compose --profile browser up -d browser

# Run tests
docker compose exec browser python browse.py <command>
```

### Commands
```bash
# Check page status
docker compose exec browser python browse.py status

# Take screenshot
docker compose exec browser python browse.py screenshot <name>

# List buttons
docker compose exec browser python browse.py buttons

# Open menu
docker compose exec browser python browse.py menu

# Click element (by data-testid or text)
docker compose exec browser python browse.py click "login-google"
docker compose exec browser python browse.py click "Button Text"
```

### Test IDs

Use `data-testid` attributes for reliable element selection:

```svelte
<button data-testid="menu-toggle">Menu</button>
<button data-testid="login-google">Google</button>
```

### Key Test IDs

| Element | data-testid | Location |
|---------|-------------|----------|
| Menu toggle | `menu-toggle` | +layout.svelte |
| Menu nav | `menu-nav` | +layout.svelte |
| Nav: Home | `nav-home` | +layout.svelte |
| Nav: Tables | `nav-tables` | +layout.svelte |
| Nav: Settings | `nav-settings` | +layout.svelte |
| Nav: Debug | `nav-debug` | +layout.svelte |
| Nav: Login | `nav-login` | +layout.svelte |
| Nav: Logout | `nav-logout` | +layout.svelte |
| Login: Authentik | `login-authentik` | login/+page.svelte |
| Login: Google | `login-google` | login/+page.svelte |

## Auth Flow

```mermaid
sequenceDiagram
    User->>Login: Click provider
    Login->>PKCE: Generate verifier/challenge
    Login->>Provider: Redirect with challenge
    Provider->>Callback: Return with code
    Callback->>Backend: Exchange code + verifier
    Backend->>Callback: Tokens + userinfo
    Callback->>Store: Save to localStorage
    Store->>Home: Redirect (authenticated)
```

## Route Protection

```svelte
<script lang="ts">
import { onMount } from 'svelte';
import { goto } from '$app/navigation';
import { authStore } from '$lib/stores/auth.store';

onMount(() => {
  if (!$authStore?.role) {
    goto('/login');
  }
});
</script>
```

## API Calls

```typescript
import { authStore } from '$lib/stores/auth.store';

const response = await fetch(`${BACKEND_URL}/api/endpoint`, {
  headers: {
    'Authorization': `Bearer ${$authStore.accessToken}`,
    'Content-Type': 'application/json'
  }
});
```

## Tables API Client

```typescript
import { fetchTables, createTable, fetchColumns, createColumn, fetchRows, createRow } from '$lib/backend/tables';

// Tables
const tables = await fetchTables();
const newTable = await createTable("My Table");

// Columns
const cols = await fetchColumns(tableId);
const newCol = await createColumn(tableId, { name: "Status", type: "select", options: {}, position: 0 });

// Rows
const rows = await fetchRows(tableId);
const newRow = await createRow(tableId, { data: { colId: "value" } });
```

## Storage API

```typescript
import { loadJson, saveJson } from '$lib/backend/storage';

// Load data
const data = await loadJson<MyType>('file.json');

// Save data
await saveJson('file.json', { key: 'value' });
```

## Common Tasks

### Add new route
1. Create `routes/<path>/+page.svelte`
2. Add auth check in `onMount` if protected
3. Add navigation in `+layout.svelte` menu

### Add new component
1. Create in `lib/components/`
2. Use Svelte 5 runes for state
3. Add `data-testid` for testable elements

### Add new store
1. Create in `lib/stores/`
2. Use `$state()` for reactive values
3. Sync to localStorage if needed
