package awconfig

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestFindWorktreeContextPathLocalOnly(t *testing.T) {
	t.Parallel()

	tmp := t.TempDir()
	root := filepath.Join(tmp, "repo")
	nested := filepath.Join(root, "a", "b", "c")
	if err := os.MkdirAll(nested, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	if err := os.MkdirAll(filepath.Join(root, ".aw"), 0o755); err != nil {
		t.Fatalf("mkdir .aw: %v", err)
	}
	ctxPath := filepath.Join(root, ".aw", "context")
	if err := os.WriteFile(ctxPath, []byte("default_account: alice\n"), 0o600); err != nil {
		t.Fatalf("write: %v", err)
	}

	// From root: found
	got, err := FindWorktreeContextPath(root)
	if err != nil {
		t.Fatalf("FindWorktreeContextPath from root: %v", err)
	}
	if got != ctxPath {
		t.Fatalf("path=%q want %q", got, ctxPath)
	}

	// From nested: NOT found (no walking up)
	_, err = FindWorktreeContextPath(nested)
	if !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("expected ErrNotExist from nested dir, got %v", err)
	}
}

func TestFindWorktreeContextPathMissing(t *testing.T) {
	t.Parallel()

	tmp := t.TempDir()
	_, err := FindWorktreeContextPath(tmp)
	if !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("err=%v, want os.ErrNotExist", err)
	}
}

func TestSaveWorktreeContextToWrites0600(t *testing.T) {
	t.Parallel()

	tmp := t.TempDir()
	path := filepath.Join(tmp, ".aw", "context")

	ctx := &WorktreeContext{
		DefaultAccount: "alice",
		ServerAccounts: map[string]string{"prod": "bob"},
	}
	if err := SaveWorktreeContextTo(path, ctx); err != nil {
		t.Fatalf("SaveWorktreeContextTo: %v", err)
	}

	info, err := os.Stat(path)
	if err != nil {
		t.Fatalf("stat: %v", err)
	}
	if got := info.Mode().Perm(); got != 0o600 {
		t.Fatalf("perm=%o, want 600", got)
	}
}

func TestSaveWorktreeContextToRoundTrip(t *testing.T) {
	t.Parallel()

	tmp := t.TempDir()
	path := filepath.Join(tmp, ".aw", "context")

	ctx := &WorktreeContext{
		DefaultAccount: "alice",
		ServerAccounts: map[string]string{"prod": "bob"},
		HumanAccount:   "human",
	}
	if err := SaveWorktreeContextTo(path, ctx); err != nil {
		t.Fatalf("SaveWorktreeContextTo: %v", err)
	}

	loaded, err := LoadWorktreeContextFrom(path)
	if err != nil {
		t.Fatalf("LoadWorktreeContextFrom: %v", err)
	}
	if loaded.DefaultAccount != "alice" {
		t.Fatalf("default_account=%s", loaded.DefaultAccount)
	}
	if loaded.ServerAccounts["prod"] != "bob" {
		t.Fatalf("server_accounts[prod]=%s", loaded.ServerAccounts["prod"])
	}
	if loaded.HumanAccount != "human" {
		t.Fatalf("human_account=%s", loaded.HumanAccount)
	}
}

func TestSaveWorktreeContextToReplacesExisting(t *testing.T) {
	t.Parallel()

	tmp := t.TempDir()
	path := filepath.Join(tmp, ".aw", "context")

	ctx1 := &WorktreeContext{DefaultAccount: "alice"}
	if err := SaveWorktreeContextTo(path, ctx1); err != nil {
		t.Fatalf("first save: %v", err)
	}

	ctx2 := &WorktreeContext{DefaultAccount: "bob"}
	if err := SaveWorktreeContextTo(path, ctx2); err != nil {
		t.Fatalf("second save: %v", err)
	}

	loaded, err := LoadWorktreeContextFrom(path)
	if err != nil {
		t.Fatalf("LoadWorktreeContextFrom: %v", err)
	}
	if loaded.DefaultAccount != "bob" {
		t.Fatalf("default_account=%s, want bob", loaded.DefaultAccount)
	}
}

func TestSaveWorktreeContextToSingleTrailingNewline(t *testing.T) {
	t.Parallel()

	tmp := t.TempDir()
	path := filepath.Join(tmp, ".aw", "context")

	ctx := &WorktreeContext{DefaultAccount: "alice"}
	if err := SaveWorktreeContextTo(path, ctx); err != nil {
		t.Fatalf("SaveWorktreeContextTo: %v", err)
	}

	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	s := string(data)
	if !strings.HasSuffix(s, "\n") {
		t.Fatal("missing trailing newline")
	}
	if strings.HasSuffix(s, "\n\n") {
		t.Fatal("double trailing newline")
	}
}

func TestSaveWorktreeContextToNoTempFileLeftBehind(t *testing.T) {
	t.Parallel()

	tmp := t.TempDir()
	dir := filepath.Join(tmp, ".aw")
	path := filepath.Join(dir, "context")

	ctx := &WorktreeContext{DefaultAccount: "alice"}
	if err := SaveWorktreeContextTo(path, ctx); err != nil {
		t.Fatalf("SaveWorktreeContextTo: %v", err)
	}

	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatalf("ReadDir: %v", err)
	}
	for _, e := range entries {
		if strings.HasPrefix(e.Name(), ".tmp.") {
			t.Fatalf("temp file left behind: %s", e.Name())
		}
	}
}
