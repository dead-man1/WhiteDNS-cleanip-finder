package main

import (
	"encoding/csv"
	"fmt"
	"os"
	"path/filepath"
)

func main() {
	// locate CSV
	cwd, _ := os.Getwd()
	csvPath := filepath.Join(cwd, "..", "IranASNs", "filtered_ipv4.csv")
	f, err := os.Open(csvPath)
	if err != nil {
		fmt.Printf("error opening CSV: %v\n", err)
		return
	}
	defer f.Close()
	r := csv.NewReader(f)
	r.Read() // skip header
	totalLines := 0
	uniqueASNs := make(map[string]int)
	for {
		rec, err := r.Read()
		if err != nil {
			break
		}
		if len(rec) < 9 {
			continue
		}
		totalLines++
		key := rec[5] + " - " + rec[6]
		uniqueASNs[key]++
	}

	totalSubnets := 0
	for _, v := range uniqueASNs {
		totalSubnets += v
	}

	fmt.Printf("Python-like ASN stats (CSV parse):\n")
	fmt.Printf(" v4 CSV lines: %d\n", totalLines)
	fmt.Printf(" unique ASNs (grouped): %d\n", len(uniqueASNs))
	fmt.Printf(" total subnets from groups: %d\n", totalSubnets)
	fmt.Printf(" csv path: %s\n", csvPath)
}
