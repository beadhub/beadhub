package run

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"unicode/utf8"
)

type promptInput struct {
	Text       string
	ImagePaths []string
}

func resolvePromptInput(text string) (promptInput, bool, error) {
	paths := resolveDroppedPaths(text)
	if len(paths) == 0 {
		return promptInput{}, false, nil
	}

	images := make([]string, 0, len(paths))
	textParts := make([]string, 0, len(paths))
	for _, path := range paths {
		info, err := os.Stat(path)
		if err != nil {
			return promptInput{}, false, err
		}
		if info.IsDir() {
			textParts = append(textParts, fmt.Sprintf("User attached directory: %s", path))
			continue
		}
		if isImagePath(path) {
			images = append(images, path)
			continue
		}
		if content, ok := readTextFile(path); ok {
			textParts = append(textParts, formatAttachedTextFile(path, string(content)))
			continue
		}
		textParts = append(textParts, fmt.Sprintf("User attached file: %s", path))
	}

	if len(images) > 0 {
		textParts = append([]string{formatAttachedImagePrompt(images)}, textParts...)
	}
	return promptInput{
		Text:       strings.TrimSpace(strings.Join(textParts, "\n\n")),
		ImagePaths: images,
	}, true, nil
}

func resolveDroppedPaths(text string) []string {
	text = strings.TrimSpace(text)
	if text == "" {
		return nil
	}

	lines := strings.Split(text, "\n")
	paths := make([]string, 0, len(lines))
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		path, ok := resolveDroppedPath(line)
		if !ok {
			return nil
		}
		paths = append(paths, path)
	}
	if len(paths) == 0 {
		return nil
	}
	return paths
}

func resolveDroppedPath(text string) (string, bool) {
	candidate := strings.TrimSpace(text)
	if candidate == "" {
		return "", false
	}
	candidate = strings.Trim(candidate, `"'`)
	candidate = unescapeShellPath(candidate)
	if !looksLikeLocalPath(candidate) {
		return "", false
	}
	if _, err := os.Stat(candidate); err == nil {
		return candidate, true
	}
	return "", false
}

func unescapeShellPath(path string) string {
	var out strings.Builder
	out.Grow(len(path))
	for i := 0; i < len(path); i++ {
		if path[i] == '\\' && i+1 < len(path) {
			i++
		}
		out.WriteByte(path[i])
	}
	return out.String()
}

func looksLikeLocalPath(path string) bool {
	if path == "" {
		return false
	}
	return filepath.IsAbs(path)
}

func isImagePath(path string) bool {
	switch strings.ToLower(filepath.Ext(path)) {
	case ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff":
		return true
	default:
		return false
	}
}

func readTextFile(path string) ([]byte, bool) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, false
	}
	if len(data) == 0 {
		return data, true
	}
	sample := data
	if len(sample) > 4096 {
		sample = sample[:4096]
	}
	if bytes.IndexByte(sample, 0) >= 0 {
		return nil, false
	}
	if !utf8.Valid(sample) {
		return nil, false
	}
	return data, true
}

func formatAttachedImagePrompt(paths []string) string {
	if len(paths) == 1 {
		return fmt.Sprintf("User attached image: %s", paths[0])
	}
	lines := []string{"User attached images:"}
	for _, path := range paths {
		lines = append(lines, "- "+path)
	}
	return strings.Join(lines, "\n")
}

func formatAttachedTextFile(path string, content string) string {
	return fmt.Sprintf("User attached text file: %s\n----- BEGIN FILE -----\n%s\n----- END FILE -----", path, strings.TrimRight(content, "\n"))
}
