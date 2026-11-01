-- Coloring Book Studio initial schema
CREATE TABLE projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  layout_revision INTEGER NOT NULL DEFAULT 1,
  is_sample INTEGER NOT NULL DEFAULT 0,
  release_approval TEXT
);

CREATE TABLE book_specs (
  project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
  data TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE style_guides (
  project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
  data TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE listings (
  project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
  data TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE scenes (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  position INTEGER NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE assets (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  display_name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  source_type TEXT NOT NULL DEFAULT 'unknown',
  creator TEXT,
  license TEXT,
  license_evidence TEXT,
  rights_declaration TEXT NOT NULL DEFAULT 'unknown',
  ai_involvement TEXT NOT NULL DEFAULT 'unknown',
  generation TEXT,
  review_status TEXT NOT NULL DEFAULT 'unreviewed',
  review_notes TEXT,
  is_demo INTEGER NOT NULL DEFAULT 0,
  current_version_id TEXT
);

CREATE TABLE asset_versions (
  id TEXT PRIMARY KEY,
  asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  parent_version_id TEXT REFERENCES asset_versions(id),
  version_no INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  storage_key TEXT NOT NULL,
  mime TEXT NOT NULL,
  width_px INTEGER NOT NULL,
  height_px INTEGER NOT NULL,
  dpi_meta_x REAL,
  dpi_meta_y REAL,
  operation TEXT,
  original_width_px INTEGER NOT NULL,
  original_height_px INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE pages (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  position INTEGER NOT NULL,
  kind TEXT NOT NULL,
  scene_id TEXT REFERENCES scenes(id) ON DELETE SET NULL,
  label TEXT,
  approved INTEGER NOT NULL DEFAULT 0,
  approved_at TEXT,
  approval_note TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE page_elements (
  id TEXT PRIMARY KEY,
  page_id TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  z INTEGER NOT NULL,
  kind TEXT NOT NULL,
  data TEXT NOT NULL
);

CREATE TABLE page_history (
  id TEXT PRIMARY KEY,
  page_id TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  reason TEXT,
  snapshot TEXT NOT NULL
);

CREATE TABLE cover_layouts (
  project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
  data TEXT NOT NULL,
  geometry TEXT NOT NULL,
  basis_layout_revision INTEGER NOT NULL,
  basis_page_count INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  status TEXT NOT NULL,
  dedupe_key TEXT,
  params TEXT NOT NULL,
  progress REAL,
  progress_label TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 2,
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  result TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX jobs_active_dedupe ON jobs(dedupe_key) WHERE status IN ('queued','running');

CREATE TABLE preflight_runs (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  layout_revision INTEGER NOT NULL,
  summary TEXT NOT NULL
);

CREATE TABLE preflight_findings (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES preflight_runs(id) ON DELETE CASCADE,
  severity TEXT NOT NULL,
  category TEXT NOT NULL,
  code TEXT NOT NULL,
  message TEXT NOT NULL,
  page_id TEXT,
  page_number INTEGER,
  detail TEXT
);

CREATE TABLE export_snapshots (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  layout_revision INTEGER NOT NULL,
  data TEXT NOT NULL
);

CREATE TABLE exports (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  snapshot_id TEXT NOT NULL REFERENCES export_snapshots(id),
  job_id TEXT,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  files TEXT,
  manifest TEXT,
  verification TEXT
);

CREATE TABLE pricing_profiles (
  id TEXT PRIMARY KEY,
  marketplace TEXT NOT NULL,
  version TEXT NOT NULL,
  checked_on TEXT NOT NULL,
  data TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE generation_requests (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  job_id TEXT,
  scene_id TEXT,
  provider TEXT NOT NULL,
  model TEXT,
  prompt TEXT NOT NULL,
  params TEXT NOT NULL,
  state TEXT NOT NULL,
  estimated_cost TEXT,
  reported_usage TEXT,
  reported_cost TEXT,
  asset_id TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
