package awid

import (
	"context"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestDIDKeyResolverValidDID(t *testing.T) {
	t.Parallel()

	pub, _, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	did := ComputeDIDKey(pub)

	r := &DIDKeyResolver{}
	identity, err := r.Resolve(context.Background(), did)
	if err != nil {
		t.Fatal(err)
	}
	if identity.DID != did {
		t.Fatalf("DID=%q, want %q", identity.DID, did)
	}
	if !identity.PublicKey.Equal(pub) {
		t.Fatal("PublicKey mismatch")
	}
	if identity.ResolvedVia != "did:key" {
		t.Fatalf("ResolvedVia=%q, want did:key", identity.ResolvedVia)
	}
	if identity.Address != "" {
		t.Fatalf("Address should be empty, got %q", identity.Address)
	}
}

func TestDIDKeyResolverInvalidDID(t *testing.T) {
	t.Parallel()

	r := &DIDKeyResolver{}
	_, err := r.Resolve(context.Background(), "not-a-did")
	if err == nil {
		t.Fatal("expected error for invalid DID")
	}
}

func TestDIDKeyResolverRejectsNonDIDKey(t *testing.T) {
	t.Parallel()

	r := &DIDKeyResolver{}
	_, err := r.Resolve(context.Background(), "mycompany/researcher")
	if err == nil {
		t.Fatal("expected error for non-did:key identifier")
	}
}

func TestServerResolverValidAddress(t *testing.T) {
	t.Parallel()

	pub, _, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	did := ComputeDIDKey(pub)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/agents/resolve/mycompany/researcher" {
			t.Fatalf("path=%s", r.URL.Path)
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"did":      did,
			"address":  "mycompany/researcher",
			"handle":   "@alice",
			"server":   "app.aweb.ai",
			"custody":  "self",
			"lifetime": "persistent",
		})
	}))
	t.Cleanup(server.Close)

	c, err := NewWithAPIKey(server.URL, "aw_sk_test")
	if err != nil {
		t.Fatal(err)
	}
	r := &ServerResolver{Client: c}
	identity, err := r.Resolve(context.Background(), "mycompany/researcher")
	if err != nil {
		t.Fatal(err)
	}
	if identity.DID != did {
		t.Fatalf("DID=%q", identity.DID)
	}
	if identity.Address != "mycompany/researcher" {
		t.Fatalf("Address=%q", identity.Address)
	}
	if identity.Handle != "@alice" {
		t.Fatalf("Handle=%q", identity.Handle)
	}
	if identity.Custody != "self" {
		t.Fatalf("Custody=%q", identity.Custody)
	}
	if identity.Lifetime != "persistent" {
		t.Fatalf("Lifetime=%q", identity.Lifetime)
	}
	if identity.ResolvedVia != "server" {
		t.Fatalf("ResolvedVia=%q", identity.ResolvedVia)
	}
}

func TestServerResolverIncludesStableIDAndPublicKey(t *testing.T) {
	t.Parallel()

	pub, _, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	did := ComputeDIDKey(pub)
	pubB64 := base64.RawStdEncoding.EncodeToString(pub)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"did":        did,
			"stable_id":  "did:aw:test123",
			"address":    "mycompany/researcher",
			"public_key": pubB64,
			"custody":    "self",
			"lifetime":   "persistent",
		})
	}))
	t.Cleanup(server.Close)

	c, err := NewWithAPIKey(server.URL, "aw_sk_test")
	if err != nil {
		t.Fatal(err)
	}
	r := &ServerResolver{Client: c}
	identity, err := r.Resolve(context.Background(), "mycompany/researcher")
	if err != nil {
		t.Fatal(err)
	}
	if identity.StableID != "did:aw:test123" {
		t.Fatalf("stable_id=%q", identity.StableID)
	}
	if identity.PublicKey == nil || !identity.PublicKey.Equal(pub) {
		t.Fatal("public_key was not decoded correctly")
	}
}

func TestServerResolverRejectsDIDPublicKeyMismatch(t *testing.T) {
	t.Parallel()

	pubA, _, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	pubB, _, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	didA := ComputeDIDKey(pubA)
	pubBB64 := base64.RawStdEncoding.EncodeToString(pubB)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"did":        didA,
			"address":    "mycompany/researcher",
			"public_key": pubBB64,
			"custody":    "self",
			"lifetime":   "persistent",
		})
	}))
	t.Cleanup(server.Close)

	c, err := NewWithAPIKey(server.URL, "aw_sk_test")
	if err != nil {
		t.Fatal(err)
	}
	r := &ServerResolver{Client: c}
	_, err = r.Resolve(context.Background(), "mycompany/researcher")
	if err == nil {
		t.Fatal("expected DID/public_key mismatch error")
	}
}

func TestPinResolverByDID(t *testing.T) {
	t.Parallel()

	ps := NewPinStore()
	did := "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"
	ps.StorePin(did, "mycompany/researcher", "@alice", "app.aweb.ai")

	r := &PinResolver{Store: ps}
	identity, err := r.Resolve(context.Background(), did)
	if err != nil {
		t.Fatal(err)
	}
	if identity.DID != did {
		t.Fatalf("DID=%q", identity.DID)
	}
	if identity.Address != "mycompany/researcher" {
		t.Fatalf("Address=%q", identity.Address)
	}
	if identity.ResolvedVia != "pin" {
		t.Fatalf("ResolvedVia=%q", identity.ResolvedVia)
	}
}

func TestPinResolverByAddress(t *testing.T) {
	t.Parallel()

	ps := NewPinStore()
	did := "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"
	ps.StorePin(did, "mycompany/researcher", "@alice", "app.aweb.ai")

	r := &PinResolver{Store: ps}
	identity, err := r.Resolve(context.Background(), "mycompany/researcher")
	if err != nil {
		t.Fatal(err)
	}
	if identity.DID != did {
		t.Fatalf("DID=%q", identity.DID)
	}
	if identity.Address != "mycompany/researcher" {
		t.Fatalf("Address=%q", identity.Address)
	}
}

func TestPinResolverNotFound(t *testing.T) {
	t.Parallel()

	ps := NewPinStore()
	r := &PinResolver{Store: ps}
	_, err := r.Resolve(context.Background(), "unknown/agent")
	if err == nil {
		t.Fatal("expected error for unknown agent")
	}
}

func TestChainResolverDispatchesByFormat(t *testing.T) {
	t.Parallel()

	pub, _, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	did := ComputeDIDKey(pub)

	// did:key identifier should use DIDKeyResolver.
	cr := &ChainResolver{
		DIDKey: &DIDKeyResolver{},
	}
	identity, err := cr.Resolve(context.Background(), did)
	if err != nil {
		t.Fatal(err)
	}
	if identity.DID != did {
		t.Fatalf("DID=%q", identity.DID)
	}
	if identity.ResolvedVia != "did:key" {
		t.Fatalf("ResolvedVia=%q", identity.ResolvedVia)
	}
}

func TestChainResolverAddressUsesServer(t *testing.T) {
	t.Parallel()

	pub, _, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	did := ComputeDIDKey(pub)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"did":      did,
			"address":  "mycompany/researcher",
			"custody":  "self",
			"lifetime": "persistent",
		})
	}))
	t.Cleanup(server.Close)

	c, err := NewWithAPIKey(server.URL, "aw_sk_test")
	if err != nil {
		t.Fatal(err)
	}

	cr := &ChainResolver{
		DIDKey: &DIDKeyResolver{},
		Server: &ServerResolver{Client: c},
	}
	identity, err := cr.Resolve(context.Background(), "mycompany/researcher")
	if err != nil {
		t.Fatal(err)
	}
	if identity.DID != did {
		t.Fatalf("DID=%q", identity.DID)
	}
	if identity.ResolvedVia != "server" {
		t.Fatalf("ResolvedVia=%q", identity.ResolvedVia)
	}
	// ChainResolver should cross-check and extract public key from DID.
	if identity.PublicKey == nil {
		t.Fatal("PublicKey should be extracted from DID")
	}
	if !identity.PublicKey.Equal(pub) {
		t.Fatal("PublicKey mismatch after cross-check")
	}
}

func TestChainResolverNoServer(t *testing.T) {
	t.Parallel()

	cr := &ChainResolver{
		DIDKey: &DIDKeyResolver{},
	}
	_, err := cr.Resolve(context.Background(), "mycompany/researcher")
	if err == nil {
		t.Fatal("expected error when no server resolver for address")
	}
}
