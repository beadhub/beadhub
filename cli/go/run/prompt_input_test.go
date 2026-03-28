package run

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestResolvePromptInputInlinesTextFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "notes.txt")
	if err := os.WriteFile(path, []byte("line one\nline two\n"), 0o644); err != nil {
		t.Fatalf("write text file: %v", err)
	}

	got, handled, err := resolvePromptInput(path)
	if err != nil {
		t.Fatalf("resolvePromptInput returned error: %v", err)
	}
	if !handled {
		t.Fatal("expected file path to be handled")
	}
	if len(got.ImagePaths) != 0 {
		t.Fatalf("expected no image paths, got %#v", got.ImagePaths)
	}
	for _, want := range []string{"User attached text file: " + path, "line one", "line two"} {
		if !strings.Contains(got.Text, want) {
			t.Fatalf("expected prompt text to contain %q, got %q", want, got.Text)
		}
	}
}

func TestResolvePromptInputCollectsImages(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "image.png")
	if err := os.WriteFile(path, []byte("png"), 0o644); err != nil {
		t.Fatalf("write image file: %v", err)
	}

	got, handled, err := resolvePromptInput(path)
	if err != nil {
		t.Fatalf("resolvePromptInput returned error: %v", err)
	}
	if !handled {
		t.Fatal("expected image path to be handled")
	}
	if len(got.ImagePaths) != 1 || got.ImagePaths[0] != path {
		t.Fatalf("unexpected image paths %#v", got.ImagePaths)
	}
	if !strings.Contains(got.Text, "User attached image: "+path) {
		t.Fatalf("unexpected image prompt text %q", got.Text)
	}
}
