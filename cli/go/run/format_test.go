package run

import "testing"

func TestFormatToolCallLinesUsesMinimalShellStyle(t *testing.T) {
	lines := formatToolCallLines(ToolCall{
		Name: "Bash",
		Input: map[string]any{
			"command": "go test ./... 2>&1",
		},
	})
	if len(lines) != 1 {
		t.Fatalf("expected one line, got %#v", lines)
	}
	if lines[0] != ">_ go test ./... 2>&1" {
		t.Fatalf("unexpected tool line %q", lines[0])
	}
}

func TestFormatToolCallLinesKeepsToolNameForNonShellTools(t *testing.T) {
	lines := formatToolCallLines(ToolCall{
		Name: "View",
		Input: map[string]any{
			"path": "/tmp/image.png",
		},
	})
	if len(lines) != 1 {
		t.Fatalf("expected one line, got %#v", lines)
	}
	if lines[0] != ">_ View /tmp/image.png" {
		t.Fatalf("unexpected tool line %q", lines[0])
	}
}
