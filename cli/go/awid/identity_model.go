package awid

import "strings"

type IdentityClass string

const (
	IdentityClassEphemeral IdentityClass = LifetimeEphemeral
	IdentityClassPermanent IdentityClass = LifetimePersistent
)

func NormalizeLifetime(lifetime string) string {
	switch strings.TrimSpace(strings.ToLower(lifetime)) {
	case "", LifetimeEphemeral:
		return LifetimeEphemeral
	case LifetimePersistent:
		return LifetimePersistent
	default:
		return strings.TrimSpace(strings.ToLower(lifetime))
	}
}

func IdentityClassFromLifetime(lifetime string) IdentityClass {
	switch NormalizeLifetime(lifetime) {
	case LifetimePersistent:
		return IdentityClassPermanent
	default:
		return IdentityClassEphemeral
	}
}

func IdentityHasPublicAddress(lifetime string) bool {
	return IdentityClassFromLifetime(lifetime) == IdentityClassPermanent
}

func RoutingHandle(alias, address, lifetime string) string {
	if strings.TrimSpace(alias) != "" {
		return strings.TrimSpace(alias)
	}
	if !IdentityHasPublicAddress(lifetime) {
		return strings.TrimSpace(address)
	}
	return ""
}

func PublicAddress(address, lifetime string) string {
	if !IdentityHasPublicAddress(lifetime) {
		return ""
	}
	return strings.TrimSpace(address)
}

func DescribeIdentityClass(lifetime string) string {
	switch IdentityClassFromLifetime(lifetime) {
	case IdentityClassPermanent:
		return "permanent"
	default:
		return "ephemeral"
	}
}

func IsSelfCustodial(custody string) bool {
	return strings.TrimSpace(strings.ToLower(custody)) == CustodySelf
}
