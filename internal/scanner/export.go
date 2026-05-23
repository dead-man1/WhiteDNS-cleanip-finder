package scanner

// This file exposes a small test helper used by the compare tool to run the
// internal response parser + classifier on raw HTTP bytes. It keeps the core
// classification logic unexported while allowing external test utilities to
// call it.

import (
	"net/http"
	"strings"
)

// ClassifyRawResponse parses a raw HTTP response and returns the classification
// string ("accept", "reject", "soft_accept", "dead").
func ClassifyRawResponse(raw []byte, domain string) string {
	status, headers, body := parseRawHTTPResponse(raw)
	// parseRawHTTPResponse returns http.Header for headers
	_ = headers // keep type
	res := classifyResponse(status, body, headers, domain)
	if res == "reject" {
		headersLower := buildHeadersLower(headers)
		respLower := headersLower + "\r\n" + strings.ToLower(string(body))
		if _, ok := tlsHTTPFallbackAcceptStatus[status]; ok && !hasNonOverridableHardReject(respLower) {
			return "accept"
		}
	}
	return res
}

// ClassifyParsedResponse is a convenience wrapper for callers that already
// have parsed components.
func ClassifyParsedResponse(status int, headers http.Header, body []byte, domain string) string {
	res := classifyResponse(status, body, headers, domain)
	if res == "reject" {
		headersLower := buildHeadersLower(headers)
		respLower := headersLower + "\r\n" + strings.ToLower(string(body))
		if _, ok := tlsHTTPFallbackAcceptStatus[status]; ok && !hasNonOverridableHardReject(respLower) {
			return "accept"
		}
	}
	return res
}
