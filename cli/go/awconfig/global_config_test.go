package awconfig

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/awebai/aw/awid"
)

func TestLoadGlobalFromMissingFileReturnsEmpty(t *testing.T) {
	t.Parallel()

	tmp := t.TempDir()
	path := filepath.Join(tmp, "config.yaml")

	cfg, err := LoadGlobalFrom(path)
	if err != nil {
		t.Fatalf("LoadGlobalFrom: %v", err)
	}
	if cfg == nil {
		t.Fatalf("expected cfg")
	}
	if cfg.Servers == nil || cfg.Accounts == nil {
		t.Fatalf("expected maps initialized")
	}
}

func TestSaveGlobalToWrites0600(t *testing.T) {
	t.Parallel()

	tmp := t.TempDir()
	path := filepath.Join(tmp, "nested", "config.yaml")

	cfg := &GlobalConfig{
		Servers: map[string]Server{
			"localhost:8000": {},
		},
		Accounts: map[string]Account{
			"alice": {Account: awid.Account{
				Server: "localhost:8000",
				APIKey: "aw_sk_test",
			}},
		},
		DefaultAccount: "alice",
	}
	if err := cfg.SaveGlobalTo(path); err != nil {
		t.Fatalf("SaveGlobalTo: %v", err)
	}

	info, err := os.Stat(path)
	if err != nil {
		t.Fatalf("stat: %v", err)
	}
	if got := info.Mode().Perm(); got != 0o600 {
		t.Fatalf("perm=%o, want 600", got)
	}
}

func TestSaveGlobalToNoTempFileLeftBehind(t *testing.T) {
	t.Parallel()

	tmp := t.TempDir()
	dir := filepath.Join(tmp, "cfg")
	path := filepath.Join(dir, "config.yaml")

	cfg := &GlobalConfig{
		Accounts: map[string]Account{
			"alice": {Account: awid.Account{APIKey: "aw_sk_test"}},
		},
	}
	if err := cfg.SaveGlobalTo(path); err != nil {
		t.Fatalf("SaveGlobalTo: %v", err)
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

func TestAccountEmailFieldRoundTrips(t *testing.T) {
	t.Parallel()

	tmp := t.TempDir()
	path := filepath.Join(tmp, "config.yaml")

	if err := UpdateGlobalAt(path, func(cfg *GlobalConfig) error {
		cfg.Accounts["alice"] = Account{Account: awid.Account{
			Server:         "localhost:8000",
			APIKey:         "aw_sk_test",
			IdentityHandle: "alice",
			Email:          "alice@example.com",
		}}
		cfg.DefaultAccount = "alice"
		return nil
	}); err != nil {
		t.Fatalf("UpdateGlobalAt: %v", err)
	}

	cfg, err := LoadGlobalFrom(path)
	if err != nil {
		t.Fatalf("LoadGlobalFrom: %v", err)
	}
	acct, ok := cfg.Accounts["alice"]
	if !ok {
		t.Fatal("missing account alice")
	}
	if acct.Email != "alice@example.com" {
		t.Fatalf("email=%q, want alice@example.com", acct.Email)
	}
}

func TestAccountIdentityFieldsRoundTrip(t *testing.T) {
	t.Parallel()

	tmp := t.TempDir()
	path := filepath.Join(tmp, "config.yaml")

	if err := UpdateGlobalAt(path, func(cfg *GlobalConfig) error {
		cfg.Accounts["alice"] = Account{Account: awid.Account{
			Server:         "localhost:8000",
			APIKey:         "aw_sk_test",
			IdentityHandle: "alice",
			DID:            "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
			SigningKey:     "~/.config/aw/keys/mycompany-alice.signing.key",
			Custody:        "self",
			Lifetime:       "persistent",
		}}
		cfg.DefaultAccount = "alice"
		return nil
	}); err != nil {
		t.Fatalf("UpdateGlobalAt: %v", err)
	}

	cfg, err := LoadGlobalFrom(path)
	if err != nil {
		t.Fatalf("LoadGlobalFrom: %v", err)
	}
	acct, ok := cfg.Accounts["alice"]
	if !ok {
		t.Fatal("missing account alice")
	}
	if acct.DID != "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK" {
		t.Fatalf("DID=%q", acct.DID)
	}
	if acct.SigningKey != "~/.config/aw/keys/mycompany-alice.signing.key" {
		t.Fatalf("SigningKey=%q", acct.SigningKey)
	}
	if acct.Custody != "self" {
		t.Fatalf("Custody=%q", acct.Custody)
	}
	if acct.Lifetime != "persistent" {
		t.Fatalf("Lifetime=%q", acct.Lifetime)
	}
}

func TestAccountIdentityFieldsOmittedWhenEmpty(t *testing.T) {
	t.Parallel()

	tmp := t.TempDir()
	path := filepath.Join(tmp, "config.yaml")

	// Save without identity fields — they should be omitted from YAML.
	cfg := &GlobalConfig{
		Accounts: map[string]Account{
			"alice": {Account: awid.Account{Server: "localhost:8000", APIKey: "aw_sk_test"}},
		},
		DefaultAccount: "alice",
	}
	if err := cfg.SaveGlobalTo(path); err != nil {
		t.Fatalf("SaveGlobalTo: %v", err)
	}

	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	yaml := string(data)
	for _, field := range []string{"did:", "signing_key:", "custody:", "lifetime:"} {
		if strings.Contains(yaml, field) {
			t.Fatalf("YAML should not contain %q when empty, got:\n%s", field, yaml)
		}
	}
}

func TestIdentityFieldsPropagateToSelection(t *testing.T) {
	t.Parallel()

	global := &GlobalConfig{
		Servers: map[string]Server{
			"prod": {URL: "https://app.aweb.ai"},
		},
		Accounts: map[string]Account{
			"alice": {Account: awid.Account{
				Server:         "prod",
				APIKey:         "aw_sk_test",
				IdentityHandle: "alice",
				DID:            "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
				SigningKey:     "/path/to/key",
				Custody:        "self",
				Lifetime:       "persistent",
			}},
		},
		DefaultAccount: "alice",
	}

	sel, err := Resolve(global, ResolveOptions{AccountName: "alice"})
	if err != nil {
		t.Fatalf("Resolve: %v", err)
	}
	if sel.DID != "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK" {
		t.Fatalf("DID=%q", sel.DID)
	}
	if sel.SigningKey != "/path/to/key" {
		t.Fatalf("SigningKey=%q", sel.SigningKey)
	}
	if sel.Custody != "self" {
		t.Fatalf("Custody=%q", sel.Custody)
	}
	if sel.Lifetime != "persistent" {
		t.Fatalf("Lifetime=%q", sel.Lifetime)
	}
}

func TestUpdateGlobalAtMergesAccounts(t *testing.T) {
	t.Parallel()

	tmp := t.TempDir()
	path := filepath.Join(tmp, "config.yaml")

	if err := UpdateGlobalAt(path, func(cfg *GlobalConfig) error {
		cfg.Accounts["a"] = Account{Account: awid.Account{Server: "localhost:8000", APIKey: "aw_sk_a"}}
		cfg.DefaultAccount = "a"
		return nil
	}); err != nil {
		t.Fatalf("UpdateGlobalAt #1: %v", err)
	}

	if err := UpdateGlobalAt(path, func(cfg *GlobalConfig) error {
		cfg.Accounts["b"] = Account{Account: awid.Account{Server: "localhost:8000", APIKey: "aw_sk_b"}}
		return nil
	}); err != nil {
		t.Fatalf("UpdateGlobalAt #2: %v", err)
	}

	cfg, err := LoadGlobalFrom(path)
	if err != nil {
		t.Fatalf("LoadGlobalFrom: %v", err)
	}
	if _, ok := cfg.Accounts["a"]; !ok {
		t.Fatalf("missing account a")
	}
	if _, ok := cfg.Accounts["b"]; !ok {
		t.Fatalf("missing account b")
	}
}
