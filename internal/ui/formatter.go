package ui

import (
	"fmt"
	"strings"
)

// UIFormatter provides enhanced UI formatting for better UX
type UIFormatter struct{}

// PrintHeader prints a formatted section header
func PrintHeader(title string) {
	fmt.Println()
	fmt.Println(strings.Repeat("=", 60))
	fmt.Printf("  %s\n", title)
	fmt.Println(strings.Repeat("=", 60))
}

// PrintSubheader prints a formatted subheader
func PrintSubheader(title string) {
	fmt.Println()
	fmt.Printf("  >> %s\n", title)
	fmt.Println(strings.Repeat("-", 58))
}

// PrintSuccess prints a success message
func PrintSuccess(msg string) {
	fmt.Printf("  [✓] %s\n", msg)
}

// PrintInfo prints an info message
func PrintInfo(msg string) {
	fmt.Printf("  [*] %s\n", msg)
}

// PrintWarning prints a warning message
func PrintWarning(msg string) {
	fmt.Printf("  [!] %s\n", msg)
}

// PrintError prints an error message
func PrintError(msg string) {
	fmt.Printf("  [✗] %s\n", msg)
}

// PrintOption prints a menu option
func PrintOption(key, desc string) {
	fmt.Printf("  [%s] %s\n", key, desc)
}

// PrintTable prints a formatted table
func PrintTable(headers []string, rows [][]string) {
	if len(headers) == 0 || len(rows) == 0 {
		return
	}

	// Calculate column widths
	colWidths := make([]int, len(headers))
	for i, h := range headers {
		colWidths[i] = len(h)
	}

	for _, row := range rows {
		for i, col := range row {
			if i < len(colWidths) && len(col) > colWidths[i] {
				colWidths[i] = len(col)
			}
		}
	}

	// Print header
	fmt.Print("  ")
	for i, h := range headers {
		fmt.Printf("%-*s  ", colWidths[i], h)
	}
	fmt.Println()

	// Print separator
	fmt.Print("  ")
	for i := range headers {
		fmt.Printf("%s  ", strings.Repeat("-", colWidths[i]))
	}
	fmt.Println()

	// Print rows
	for _, row := range rows {
		fmt.Print("  ")
		for i, col := range row {
			if i < len(colWidths) {
				fmt.Printf("%-*s  ", colWidths[i], col)
			}
		}
		fmt.Println()
	}
}

// PrintStats prints formatted statistics
func PrintStats(stats map[string]interface{}) {
	PrintSubheader("Statistics")
	for key, val := range stats {
		fmt.Printf("  %-25s: %v\n", key, val)
	}
}

// PrintProgress prints a progress bar
func PrintProgressBar(current, total int64, label string) {
	if total <= 0 {
		return
	}

	percentage := float64(current) * 100.0 / float64(total)
	barLength := 30
	filledLength := int(float64(barLength) * float64(current) / float64(total))

	bar := strings.Repeat("█", filledLength) + strings.Repeat("░", barLength-filledLength)
	fmt.Printf("  %s [%s] %.1f%% (%d/%d)\n", label, bar, percentage, current, total)
}

// ClearScreen clears the console screen (simple approach)
func ClearScreen() {
	fmt.Print("\033[2J\033[H")
}

// PrintMenu prints a formatted menu
func PrintMenu(title string, options map[string]string) {
	PrintHeader(title)
	for key := range options {
		PrintOption(key, options[key])
	}
	fmt.Println()
}

// PromptChoice prompts user for a choice
func PromptChoice(prompt string) string {
	fmt.Print(prompt)
	var input string
	fmt.Scanln(&input)
	return strings.TrimSpace(input)
}

// PromptYesNo prompts user for yes/no
func PromptYesNo(prompt string) bool {
	response := PromptChoice(prompt + " [y/n]: ")
	return strings.ToLower(response) == "y" || strings.ToLower(response) == "yes"
}

// PrintDivider prints a visual divider
func PrintDivider() {
	fmt.Println(strings.Repeat("-", 60))
}

// FormatNumber formats a number with thousands separator
func FormatNumber(n int64) string {
	if n < 1000 {
		return fmt.Sprintf("%d", n)
	}
	if n < 1000000 {
		return fmt.Sprintf("%d,%03d", n/1000, n%1000)
	}
	return fmt.Sprintf("%d,%03d,%03d", n/1000000, (n%1000000)/1000, n%1000)
}
