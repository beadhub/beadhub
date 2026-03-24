package awid

import (
	"crypto/ed25519"
	"encoding/hex"
	"testing"
)

func TestComputeDIDKey(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name   string
		pubHex string
		want   string
	}{
		{
			"W3C vector 1",
			"2e6fcce36701dc791488e0d0b1745cc1e33a4c1c9fcc41c63bd343dbbe0970e6",
			"did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
		},
		{
			"W3C vector 2",
			"095f9a1a595dde755d82786864ad03dfa5a4fbd68832566364e2b65e13cc9e44",
			"did:key:z6Mkf5rGMoatrSj1f4CyvuHBeXJELe9RPdzo2PKGNCKVtZxP",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			pub, err := hex.DecodeString(tc.pubHex)
			if err != nil {
				t.Fatalf("bad test hex: %v", err)
			}
			got := ComputeDIDKey(ed25519.PublicKey(pub))
			if got != tc.want {
				t.Fatalf("ComputeDIDKey()=%q, want %q", got, tc.want)
			}
		})
	}
}

func TestExtractPublicKey(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name      string
		did       string
		wantHex   string
		wantError bool
	}{
		{
			"W3C vector 1",
			"did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
			"2e6fcce36701dc791488e0d0b1745cc1e33a4c1c9fcc41c63bd343dbbe0970e6",
			false,
		},
		{
			"W3C vector 2",
			"did:key:z6Mkf5rGMoatrSj1f4CyvuHBeXJELe9RPdzo2PKGNCKVtZxP",
			"095f9a1a595dde755d82786864ad03dfa5a4fbd68832566364e2b65e13cc9e44",
			false,
		},
		{"empty string", "", "", true},
		{"wrong prefix", "did:web:example.com", "", true},
		{"missing z prefix", "did:key:6MkhaXgBZD", "", true},
		{"truncated", "did:key:z6Mk", "", true},
		{"wrong multicodec", "did:key:z3u2RDonZ81AFKiw8QCPKcsyg8Yy2MmYQNxfBn51SS2QmMiw", "", true},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			pub, err := ExtractPublicKey(tc.did)
			if tc.wantError {
				if err == nil {
					t.Fatalf("expected error, got key %x", pub)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			gotHex := hex.EncodeToString(pub)
			if gotHex != tc.wantHex {
				t.Fatalf("got %s, want %s", gotHex, tc.wantHex)
			}
		})
	}
}

func TestComputeExtractRoundtrip(t *testing.T) {
	t.Parallel()

	// Generate a fresh keypair and verify roundtrip.
	pub, _, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("GenerateKey: %v", err)
	}

	did := ComputeDIDKey(pub)

	extracted, err := ExtractPublicKey(did)
	if err != nil {
		t.Fatalf("ExtractPublicKey: %v", err)
	}

	if !pub.Equal(extracted) {
		t.Fatalf("roundtrip failed: original %x, extracted %x", pub, extracted)
	}
}
