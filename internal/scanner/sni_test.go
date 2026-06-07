package scanner

import (
	"crypto/x509"
	"testing"
	"time"
	"crypto/tls"
)

func TestCertMatchesDomainTrue(t *testing.T) {
	cert := &x509.Certificate{DNSNames: []string{"workers.dev"}}
	state := tls.ConnectionState{PeerCertificates: []*x509.Certificate{cert}}
	if !certMatchesDomain(state, "workers.dev") {
		t.Fatalf("expected certMatchesDomain to return true for workers.dev")
	}
}

func TestCertMatchesDomainFalse(t *testing.T) {
	cert := &x509.Certificate{DNSNames: []string{"example.com"}}
	state := tls.ConnectionState{PeerCertificates: []*x509.Certificate{cert}}
	if certMatchesDomain(state, "workers.dev") {
		t.Fatalf("expected certMatchesDomain to return false for mismatch")
	}
}

func TestLooksLikeHTMLResponse(t *testing.T) {
	if !looksLikeHTMLResponse([]byte("<!doctype html><html><body>Hello</body></html>")) {
		t.Fatalf("expected HTML detection to succeed")
	}
	if looksLikeHTMLResponse([]byte("{\"host\": \"workers.dev\"}")) {
		t.Fatalf("expected JSON not to be detected as HTML")
	}
}

func TestNewScannerDefaults(t *testing.T) {
	cfg := &ScannerConfig{}
	s := NewScanner(cfg)
	_ = s
	// NewScanner should set package flags from cfg (defaults to true)
	if !probeRequireHTMLForDomainTokens {
		t.Fatalf("expected probeRequireHTMLForDomainTokens to be true by default")
	}
	if !probeAcceptOnCertMatch {
		t.Fatalf("expected probeAcceptOnCertMatch to be true by default")
	}
	// allow a quick no-op sleep to simulate scanner lifecycle
	time.Sleep(10 * time.Millisecond)
}
