-- Story text printed on the left-hand page facing each illustration (optional "story pages" layout).
CREATE TABLE page_stories (
  page_id TEXT PRIMARY KEY REFERENCES pages(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title TEXT,
  text TEXT NOT NULL DEFAULT '',
  meta TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_page_stories_project ON page_stories(project_id);
