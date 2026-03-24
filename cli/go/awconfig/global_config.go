package awconfig

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/awebai/aw/awid"
	"gopkg.in/yaml.v3"
)

type GlobalConfig struct {
	Servers               map[string]Server  `yaml:"servers,omitempty"`
	Accounts              map[string]Account `yaml:"accounts,omitempty"`
	DefaultAccount        string             `yaml:"default_account,omitempty"`
	ClientDefaultAccounts map[string]string  `yaml:"client_default_accounts,omitempty"`
}

type Server struct {
	URL string `yaml:"url,omitempty"`
}

type Account struct {
	awid.Account   `yaml:",inline"`
	DefaultProject string `yaml:"default_project,omitempty"`
}

func DefaultGlobalConfigPath() (string, error) {
	if p := strings.TrimSpace(os.Getenv("AW_CONFIG_PATH")); p != "" {
		return p, nil
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, ".config", "aw", "config.yaml"), nil
}

// KeysDir returns the keys directory for a given config file path
// (e.g. "~/.config/aw/config.yaml" → "~/.config/aw/keys").
func KeysDir(configPath string) string {
	return filepath.Join(filepath.Dir(configPath), "keys")
}

func LoadGlobal() (*GlobalConfig, error) {
	path, err := DefaultGlobalConfigPath()
	if err != nil {
		return nil, err
	}
	return LoadGlobalFrom(path)
}

func LoadGlobalFrom(path string) (*GlobalConfig, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return &GlobalConfig{
				Servers:  map[string]Server{},
				Accounts: map[string]Account{},
			}, nil
		}
		return nil, err
	}

	var cfg GlobalConfig
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, err
	}
	if cfg.Servers == nil {
		cfg.Servers = map[string]Server{}
	}
	if cfg.Accounts == nil {
		cfg.Accounts = map[string]Account{}
	}
	if cfg.ClientDefaultAccounts == nil {
		cfg.ClientDefaultAccounts = map[string]string{}
	}
	return &cfg, nil
}

func (c *GlobalConfig) SaveGlobal() error {
	path, err := DefaultGlobalConfigPath()
	if err != nil {
		return err
	}
	return c.SaveGlobalTo(path)
}

func (c *GlobalConfig) SaveGlobalTo(path string) error {
	if c.Servers == nil {
		c.Servers = map[string]Server{}
	}
	if c.Accounts == nil {
		c.Accounts = map[string]Account{}
	}
	if c.ClientDefaultAccounts == nil {
		c.ClientDefaultAccounts = map[string]string{}
	}

	data, err := yaml.Marshal(c)
	if err != nil {
		return err
	}

	return atomicWriteFile(path, data)
}

// atomicWriteFile writes data to path using temp-file-and-rename
// with 0600 permissions (suitable for secrets).
func atomicWriteFile(path string, data []byte) error {
	return atomicWriteFileMode(path, data, 0o600)
}

// atomicWriteFileMode writes data to path using temp-file-and-rename.
// The temp file is chmod'd to mode before any data is written.
func atomicWriteFileMode(path string, data []byte, mode os.FileMode) error {
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return err
	}

	tmp, err := os.CreateTemp(dir, ".tmp.*")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	defer func() { _ = os.Remove(tmpName) }()

	if err := tmp.Chmod(mode); err != nil {
		_ = tmp.Close()
		return err
	}
	if _, err := tmp.Write(data); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}

	return os.Rename(tmpName, path)
}

func UpdateGlobal(fn func(cfg *GlobalConfig) error) error {
	path, err := DefaultGlobalConfigPath()
	if err != nil {
		return err
	}
	return UpdateGlobalAt(path, fn)
}

func UpdateGlobalAt(path string, fn func(cfg *GlobalConfig) error) error {
	if fn == nil {
		return errors.New("nil update function")
	}

	lockPath := path + ".lock"
	lock, err := LockExclusive(lockPath)
	if err != nil {
		return fmt.Errorf("lock global config: %w", err)
	}
	defer func() { _ = lock.Close() }()

	cfg, err := LoadGlobalFrom(path)
	if err != nil {
		return err
	}
	if err := fn(cfg); err != nil {
		return err
	}
	return cfg.SaveGlobalTo(path)
}
