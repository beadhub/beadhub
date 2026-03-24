package awid

import (
	"context"
	"testing"
)

func TestCheckTOFUPinStablePinDegradedAcceptsKnownDIDKey(t *testing.T) {
	// If an address is pinned by stable_id, but stable ID verification is unavailable
	// (client has no stable_registry client / registry unreachable), the client falls back
	// to pinning by did:key. That must not cause a false IdentityMismatch as long
	// as the did:key matches what we last verified for the stable_id pin.
	c, err := New("http://example")
	if err != nil {
		t.Fatal(err)
	}

	ps := NewPinStore()
	c.SetPinStore(ps, "")

	addr := "juan/merlin"
	stableID := "did:aw:49RVkxsgqYDxawqpb77fvYEmHw1t"
	did := "did:key:z6Mks3e5U8apRpvF9c8mpPGZ3TQyeG2gXpv4qcbF8DvnVSpB"

	ps.StorePin(stableID, addr, "", "")
	ps.Pins[stableID].StableID = stableID
	ps.Pins[stableID].DIDKey = did

	status := c.CheckTOFUPin(context.Background(), Verified, addr, did, stableID, nil, nil)
	if status != Verified {
		t.Fatalf("status=%q, want %q", status, Verified)
	}
}

func TestCheckTOFUPinStablePinDegradedRejectsChangedDIDKey(t *testing.T) {
	c, err := New("http://example")
	if err != nil {
		t.Fatal(err)
	}

	ps := NewPinStore()
	c.SetPinStore(ps, "")

	addr := "juan/merlin"
	stableID := "did:aw:49RVkxsgqYDxawqpb77fvYEmHw1t"
	didPinned := "did:key:z6Mks3e5U8apRpvF9c8mpPGZ3TQyeG2gXpv4qcbF8DvnVSpB"
	didNew := "did:key:z6MktvG6qJusedKvbECR7XVTuiYzs5J689AgnDM9GosTtKSU"

	ps.StorePin(stableID, addr, "", "")
	ps.Pins[stableID].StableID = stableID
	ps.Pins[stableID].DIDKey = didPinned

	status := c.CheckTOFUPin(context.Background(), Verified, addr, didNew, stableID, nil, nil)
	if status != IdentityMismatch {
		t.Fatalf("status=%q, want %q", status, IdentityMismatch)
	}
}
