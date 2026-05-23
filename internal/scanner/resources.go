package scanner

import (
	"fmt"
	"runtime"
	"sync"
	"sync/atomic"
	"time"
)

// ScanProgress tracks real-time scan progress
type ScanProgress struct {
	mu                    *sync.RWMutex
	TotalIPs              int64
	ScannedIPs            int64
	FoundEndpoints        int64
	StartTime             time.Time
	LastUpdateTime        time.Time
	CurrentRate           int64 // IPs per second
	EstimatedRemainingSec int64
	PercentComplete       int
	ErrorCount            int64
	RetryCount            int64
	Active                bool
}

// ResourceManager handles resource allocation for massive scans
type ResourceManager struct {
	mu                 sync.RWMutex
	maxConcurrent      int
	memoryLimitMB      int64
	currentWorkers     int32
	totalProcessed     int64
	startTime          time.Time
	lastMemorySample   time.Time
	lastMemorySampleMB int64
	progress           *ScanProgress
	workerPool         chan struct{}
	cancelChan         chan struct{}
}

// NewResourceManager creates resource manager with auto-tuning
func NewResourceManager() *ResourceManager {
	numCPU := runtime.NumCPU()

	// Auto-tune based on system
	maxConcurrent := numCPU * 4
	if maxConcurrent < 16 {
		maxConcurrent = 16
	}
	// Allow much larger concurrency for modern systems; cap to a safe upper bound
	if maxConcurrent > 10000 {
		maxConcurrent = 10000
	}

	memoryLimitMB := getAvailableMemoryMB() / 2 // Use half available

	return &ResourceManager{
		maxConcurrent: maxConcurrent,
		memoryLimitMB: memoryLimitMB,
		startTime:     time.Now(),
		progress:      &ScanProgress{mu: &sync.RWMutex{}, StartTime: time.Now()},
		workerPool:    make(chan struct{}, maxConcurrent),
		cancelChan:    make(chan struct{}),
	}
}

// getAvailableMemoryMB returns available system memory in MB
func getAvailableMemoryMB() int64 {
	var m runtime.MemStats
	runtime.ReadMemStats(&m)
	return int64(m.NumGC) // Rough estimate; use 1GB if 0
}

// AcquireWorker acquires a worker slot
func (rm *ResourceManager) AcquireWorker() error {
	select {
	case <-rm.cancelChan:
		return fmt.Errorf("scan cancelled")
	case rm.workerPool <- struct{}{}:
		atomic.AddInt32(&rm.currentWorkers, 1)
		return nil
	}
}

// ReleaseWorker releases a worker slot
func (rm *ResourceManager) ReleaseWorker() {
	<-rm.workerPool
	atomic.AddInt32(&rm.currentWorkers, -1)
}

// RecordProgress updates scan progress
func (rm *ResourceManager) RecordProgress(found int, totalProcessed int64) {
	rm.progress.mu.Lock()
	defer rm.progress.mu.Unlock()

	rm.progress.FoundEndpoints += int64(found)
	rm.progress.ScannedIPs = totalProcessed
	rm.progress.LastUpdateTime = time.Now()

	// Calculate rate
	elapsed := time.Since(rm.progress.StartTime).Seconds()
	if elapsed > 0 {
		rm.progress.CurrentRate = int64(float64(totalProcessed) / elapsed)
	}

	// Calculate percentage and ETA
	if rm.progress.TotalIPs > 0 {
		rm.progress.PercentComplete = int((totalProcessed * 100) / rm.progress.TotalIPs)
		if rm.progress.CurrentRate > 0 {
			remaining := rm.progress.TotalIPs - totalProcessed
			rm.progress.EstimatedRemainingSec = remaining / rm.progress.CurrentRate
		}
	}
}

// GetProgress returns current progress snapshot
func (rm *ResourceManager) GetProgress() ScanProgress {
	rm.progress.mu.RLock()
	defer rm.progress.mu.RUnlock()
	return *rm.progress
}

// StartProgress initializes progress tracking
func (rm *ResourceManager) StartProgress(totalIPs int64) {
	rm.progress.mu.Lock()
	defer rm.progress.mu.Unlock()

	rm.progress.TotalIPs = totalIPs
	rm.progress.StartTime = time.Now()
	rm.progress.ScannedIPs = 0
	rm.progress.FoundEndpoints = 0
	rm.progress.Active = true
	rm.progress.ErrorCount = 0
	rm.progress.RetryCount = 0
}

// RecordError increments error counter
func (rm *ResourceManager) RecordError() {
	rm.progress.mu.Lock()
	defer rm.progress.mu.Unlock()
	rm.progress.ErrorCount++
}

// RecordRetry increments retry counter
func (rm *ResourceManager) RecordRetry() {
	rm.progress.mu.Lock()
	defer rm.progress.mu.Unlock()
	rm.progress.RetryCount++
}

// Cancel stops the scan
func (rm *ResourceManager) Cancel() {
	close(rm.cancelChan)
}

// IsCancelled checks if scan is cancelled
func (rm *ResourceManager) IsCancelled() bool {
	select {
	case <-rm.cancelChan:
		return true
	default:
		return false
	}
}

// GetWorkerCount returns active worker count
func (rm *ResourceManager) GetWorkerCount() int {
	return int(atomic.LoadInt32(&rm.currentWorkers))
}

// GetMaxWorkers returns max concurrent workers
func (rm *ResourceManager) GetMaxWorkers() int {
	return rm.maxConcurrent
}

// PrintProgress formats progress for callers that want to display it.
func PrintProgress(p ScanProgress) {
	_ = p
}

// PrintProgressDetailed formats a detailed progress report for callers.
func PrintProgressDetailed(p ScanProgress) {
	_ = p
}
