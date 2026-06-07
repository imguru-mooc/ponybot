# Go 3일차 — 도전 과제 및 복습 과제 솔루션

> 3일차 강의 자료의 도전 과제(7교시 Producer-Consumer 확장)와 복습 과제(고루틴 누수 탐지, Fan-out/Fan-in, RWMutex vs sync.Map, Bounded worker pool) 솔루션입니다.

---

## 📑 목차

| 구분 | 과제 | 난이도 |
|---|---|---|
| 복습 ① | 고루틴 누수 탐지기 | ⭐⭐ |
| 복습 ② | Fan-out / Fan-in 파이프라인 (제곱 + 총합) | ⭐⭐ |
| 복습 ③ | Read-heavy 캐시 — `RWMutex` vs `sync.Map` 벤치마크 | ⭐⭐⭐ |
| 복습 ④ | Bounded worker pool (세마포어 채널) | ⭐⭐ |
| 도전 ① | 메트릭 추가 (Producer/Consumer 처리 개수) | ⭐⭐ |
| 도전 ② | 백프레셔 측정 | ⭐⭐⭐ |
| 도전 ③ | Dynamic worker pool | ⭐⭐⭐⭐ |
| 도전 ④ | Priority queue | ⭐⭐⭐ |

---

# 복습 과제 ① — 고루틴 누수 탐지기

## 문제

`runtime.NumGoroutine()`을 1초마다 출력하는 모니터 작성, 의도적으로 누수를 만들어 증가 관찰.

## 솔루션 — `leak_monitor.go`

```go
package main

import (
    "context"
    "fmt"
    "runtime"
    "time"
)

// 모니터: 주기적으로 고루틴 수 출력
func monitor(ctx context.Context, interval time.Duration) {
    ticker := time.NewTicker(interval)
    defer ticker.Stop()

    baseline := runtime.NumGoroutine()
    fmt.Printf("[모니터] 기준선: %d 고루틴\n", baseline)

    for {
        select {
        case <-ctx.Done():
            fmt.Printf("[모니터] 종료. 최종: %d\n", runtime.NumGoroutine())
            return
        case <-ticker.C:
            current := runtime.NumGoroutine()
            delta := current - baseline
            indicator := ""
            if delta > 0 {
                indicator = fmt.Sprintf(" 🚨 누수 의심 (+%d)", delta)
            }
            fmt.Printf("[모니터] 현재: %d%s\n", current, indicator)
        }
    }
}

// 누수 시나리오 1: 종료되지 않는 고루틴
func leakingFunc() {
    ch := make(chan int)
    go func() {
        // 영원히 수신 대기 (송신자 없음)
        <-ch
        fmt.Println("이건 절대 출력 안 됨")
    }()
    // ch에 아무도 송신하지 않음 → 고루틴 영원히 살아있음
}

// 누수 시나리오 2: ticker stop 안 함
func leakingTicker() {
    go func() {
        ticker := time.NewTicker(100 * time.Millisecond)
        // defer ticker.Stop() 빠뜨림
        for range ticker.C {
            // 영원히 동작
        }
    }()
}

// 안전한 함수: ctx로 종료 가능
func safeFunc(ctx context.Context) {
    go func() {
        for {
            select {
            case <-ctx.Done():
                return
            case <-time.After(time.Second):
                // 작업
            }
        }
    }()
}

func main() {
    ctx, cancel := context.WithCancel(context.Background())
    defer cancel()

    // 모니터 시작
    go monitor(ctx, 500*time.Millisecond)

    time.Sleep(time.Second)
    fmt.Println("\n--- 안전한 고루틴 5개 시작 (ctx로 관리) ---")
    safeCtx, safeCancel := context.WithCancel(context.Background())
    for i := 0; i < 5; i++ {
        safeFunc(safeCtx)
    }

    time.Sleep(2 * time.Second)
    fmt.Println("\n--- 누수 시나리오 1 발동: 10번 호출 ---")
    for i := 0; i < 10; i++ {
        leakingFunc()
    }

    time.Sleep(2 * time.Second)
    fmt.Println("\n--- 누수 시나리오 2 발동: 5번 호출 ---")
    for i := 0; i < 5; i++ {
        leakingTicker()
    }

    time.Sleep(2 * time.Second)
    fmt.Println("\n--- 안전한 고루틴 정리 ---")
    safeCancel()

    time.Sleep(2 * time.Second)
    fmt.Println("\n--- 메인 종료 (누수된 고루틴은 영원히 남음) ---")
}
```

## 실행 결과 예시

```
[모니터] 기준선: 2 고루틴
[모니터] 현재: 2

--- 안전한 고루틴 5개 시작 (ctx로 관리) ---
[모니터] 현재: 7 🚨 누수 의심 (+5)
[모니터] 현재: 7 🚨 누수 의심 (+5)

--- 누수 시나리오 1 발동: 10번 호출 ---
[모니터] 현재: 17 🚨 누수 의심 (+15)
[모니터] 현재: 17 🚨 누수 의심 (+15)

--- 누수 시나리오 2 발동: 5번 호출 ---
[모니터] 현재: 22 🚨 누수 의심 (+20)
[모니터] 현재: 22 🚨 누수 의심 (+20)

--- 안전한 고루틴 정리 ---
[모니터] 현재: 17 🚨 누수 의심 (+15)
[모니터] 현재: 17 🚨 누수 의심 (+15)
```

**`leakingFunc()`은 ctx로 제어할 수 없으므로** safeCancel() 후에도 17개가 남습니다. 누수 패턴이 명확히 보입니다.

## 학습 포인트

| 패턴 | 누수 여부 |
|---|---|
| 채널 수신 대기 + 송신자 없음 | 🚨 누수 |
| `ticker` + `Stop()` 빠짐 | 🚨 누수 |
| `for-select` + `<-ctx.Done()` 미포함 | 🚨 누수 |
| `ctx.Done()` 감시 + cancel 호출 | ✅ 안전 |

운영 환경에서는 `runtime.NumGoroutine()`을 **Prometheus 메트릭으로 노출**해 모니터링하는 것이 표준입니다.

---

# 복습 과제 ② — Fan-out / Fan-in 파이프라인

## 문제

정수 슬라이스를 받아 → 제곱하고(N개 워커 fan-out) → 결과 합치기(fan-in) → 총합 계산.

## 솔루션 — `fanout_fanin.go`

```go
package main

import (
    "context"
    "fmt"
    "sync"
    "time"
)

// Stage 1: 정수 생성
func generate(ctx context.Context, nums []int) <-chan int {
    out := make(chan int)
    go func() {
        defer close(out)
        for _, n := range nums {
            select {
            case out <- n:
            case <-ctx.Done():
                return
            }
        }
    }()
    return out
}

// Stage 2 (Fan-out): 제곱 워커
func square(ctx context.Context, in <-chan int) <-chan int {
    out := make(chan int)
    go func() {
        defer close(out)
        for n := range in {
            // CPU 부하 시뮬레이션
            time.Sleep(10 * time.Millisecond)
            select {
            case out <- n * n:
            case <-ctx.Done():
                return
            }
        }
    }()
    return out
}

// Stage 3 (Fan-in): 여러 채널 합치기
func merge(ctx context.Context, channels ...<-chan int) <-chan int {
    var wg sync.WaitGroup
    out := make(chan int)

    output := func(c <-chan int) {
        defer wg.Done()
        for v := range c {
            select {
            case out <- v:
            case <-ctx.Done():
                return
            }
        }
    }

    wg.Add(len(channels))
    for _, c := range channels {
        go output(c)
    }

    go func() {
        wg.Wait()
        close(out)
    }()

    return out
}

// Stage 4 (Sink): 총합
func sum(in <-chan int) int {
    total := 0
    for v := range in {
        total += v
    }
    return total
}

// 전체 파이프라인을 함수로 래핑
func parallelSumOfSquares(nums []int, numWorkers int) (int, time.Duration) {
    ctx, cancel := context.WithCancel(context.Background())
    defer cancel()

    start := time.Now()

    // 1. 생성
    input := generate(ctx, nums)

    // 2. Fan-out: numWorkers개 워커가 같은 채널에서 소비
    workers := make([]<-chan int, numWorkers)
    for i := 0; i < numWorkers; i++ {
        workers[i] = square(ctx, input)
    }

    // 3. Fan-in
    merged := merge(ctx, workers...)

    // 4. 총합
    total := sum(merged)

    return total, time.Since(start)
}

// 비교: 순차 처리
func sequentialSumOfSquares(nums []int) (int, time.Duration) {
    start := time.Now()
    total := 0
    for _, n := range nums {
        time.Sleep(10 * time.Millisecond) // 같은 부하
        total += n * n
    }
    return total, time.Since(start)
}

func main() {
    // 1~20을 처리
    nums := make([]int, 20)
    for i := range nums {
        nums[i] = i + 1
    }

    // 순차
    seqTotal, seqTime := sequentialSumOfSquares(nums)
    fmt.Printf("순차:   합=%d, 시간=%v\n", seqTotal, seqTime)

    // 병렬 (워커 수 다양화)
    for _, w := range []int{1, 2, 4, 8} {
        total, elapsed := parallelSumOfSquares(nums, w)
        fmt.Printf("워커 %d개: 합=%d, 시간=%v (%.1fx 가속)\n",
            w, total, elapsed, float64(seqTime)/float64(elapsed))
    }
}
```

## 실행 결과 예시

```
순차:   합=2870, 시간=205.123ms
워커 1개: 합=2870, 시간=210.456ms (1.0x 가속)
워커 2개: 합=2870, 시간=105.789ms (1.9x 가속)
워커 4개: 합=2870, 시간=56.234ms (3.6x 가속)
워커 8개: 합=2870, 시간=32.567ms (6.3x 가속)
```

(시스템에 따라 다름; CPU 코어 수가 한계)

## 학습 포인트

- **결과는 동일** (2870 = 1²+2²+...+20²)
- **워커 수에 비례해 시간 단축** (CPU 코어 수까지)
- 모든 단계가 ctx로 통일된 취소 가능
- 각 단계가 독립 함수로 분리되어 **재사용 가능**

## 정확성 검증 — 단위 테스트

```go
func TestParallelSumOfSquares(t *testing.T) {
    nums := []int{1, 2, 3, 4, 5}
    expected := 55 // 1+4+9+16+25
    for _, w := range []int{1, 2, 4} {
        total, _ := parallelSumOfSquares(nums, w)
        if total != expected {
            t.Errorf("워커 %d: got %d, want %d", w, total, expected)
        }
    }
}
```

워커 수가 달라도 **결과는 항상 동일**해야 함을 검증합니다.

---

# 복습 과제 ③ — Read-heavy 캐시 비교

## 문제

`RWMutex`를 쓴 캐시와 `sync.Map`을 쓴 캐시를 벤치마크로 비교.

## 솔루션 — `cache_bench/main_test.go`

```bash
mkdir -p ~/go-class/day3-solutions/cache_bench
cd ~/go-class/day3-solutions/cache_bench
go mod init cachebench
```

`cache.go`:

```go
package cachebench

import "sync"

// Cache 인터페이스
type Cache interface {
    Get(key string) (string, bool)
    Set(key, value string)
}

// 구현 1: map + sync.RWMutex
type RWMutexCache struct {
    rw sync.RWMutex
    m  map[string]string
}

func NewRWMutexCache() *RWMutexCache {
    return &RWMutexCache{m: make(map[string]string)}
}

func (c *RWMutexCache) Get(key string) (string, bool) {
    c.rw.RLock()
    defer c.rw.RUnlock()
    v, ok := c.m[key]
    return v, ok
}

func (c *RWMutexCache) Set(key, value string) {
    c.rw.Lock()
    defer c.rw.Unlock()
    c.m[key] = value
}

// 구현 2: sync.Map
type SyncMapCache struct {
    m sync.Map
}

func NewSyncMapCache() *SyncMapCache {
    return &SyncMapCache{}
}

func (c *SyncMapCache) Get(key string) (string, bool) {
    v, ok := c.m.Load(key)
    if !ok {
        return "", false
    }
    return v.(string), true
}

func (c *SyncMapCache) Set(key, value string) {
    c.m.Store(key, value)
}
```

`cache_test.go`:

```go
package cachebench

import (
    "fmt"
    "sync"
    "testing"
)

// 미리 데이터 채우기
func populate(c Cache, n int) {
    for i := 0; i < n; i++ {
        c.Set(fmt.Sprintf("key-%d", i), fmt.Sprintf("value-%d", i))
    }
}

// Read-heavy 시나리오: 95% Read, 5% Write
func benchmarkCache(b *testing.B, c Cache, readRatio float64) {
    populate(c, 1000)

    b.ResetTimer()
    b.RunParallel(func(pb *testing.PB) {
        i := 0
        for pb.Next() {
            key := fmt.Sprintf("key-%d", i%1000)
            if float64(i%100)/100 < readRatio {
                c.Get(key)
            } else {
                c.Set(key, "updated")
            }
            i++
        }
    })
}

// === Read 100% ===
func BenchmarkRWMutex_AllRead(b *testing.B)  { benchmarkCache(b, NewRWMutexCache(), 1.0) }
func BenchmarkSyncMap_AllRead(b *testing.B)  { benchmarkCache(b, NewSyncMapCache(), 1.0) }

// === Read 95%, Write 5% ===
func BenchmarkRWMutex_Read95(b *testing.B)   { benchmarkCache(b, NewRWMutexCache(), 0.95) }
func BenchmarkSyncMap_Read95(b *testing.B)   { benchmarkCache(b, NewSyncMapCache(), 0.95) }

// === Read 50%, Write 50% ===
func BenchmarkRWMutex_Read50(b *testing.B)   { benchmarkCache(b, NewRWMutexCache(), 0.5) }
func BenchmarkSyncMap_Read50(b *testing.B)   { benchmarkCache(b, NewSyncMapCache(), 0.5) }

// 단일 고루틴 — sync.Map 오버헤드 측정용
func BenchmarkRWMutex_Single(b *testing.B) {
    c := NewRWMutexCache()
    populate(c, 1000)
    b.ResetTimer()
    for i := 0; i < b.N; i++ {
        c.Get(fmt.Sprintf("key-%d", i%1000))
    }
}

func BenchmarkSyncMap_Single(b *testing.B) {
    c := NewSyncMapCache()
    populate(c, 1000)
    b.ResetTimer()
    for i := 0; i < b.N; i++ {
        c.Get(fmt.Sprintf("key-%d", i%1000))
    }
}

// 추가: race 안정성 검증
func TestConcurrentSafe(t *testing.T) {
    for _, c := range []Cache{NewRWMutexCache(), NewSyncMapCache()} {
        var wg sync.WaitGroup
        for i := 0; i < 100; i++ {
            wg.Add(2)
            go func(i int) { defer wg.Done(); c.Set(fmt.Sprintf("k%d", i), "v") }(i)
            go func(i int) { defer wg.Done(); c.Get(fmt.Sprintf("k%d", i)) }(i)
        }
        wg.Wait()
    }
}
```

## 실행

```bash
go test -race ./...
go test -bench=. -benchmem
```

## 전형적 결과 (8코어 머신)

```
BenchmarkRWMutex_AllRead-8     50000000   25 ns/op    0 B/op   0 allocs/op
BenchmarkSyncMap_AllRead-8     30000000   45 ns/op    0 B/op   0 allocs/op

BenchmarkRWMutex_Read95-8      30000000   40 ns/op    0 B/op   0 allocs/op
BenchmarkSyncMap_Read95-8      30000000   48 ns/op    0 B/op   0 allocs/op

BenchmarkRWMutex_Read50-8      10000000  130 ns/op    0 B/op   0 allocs/op
BenchmarkSyncMap_Read50-8      15000000   85 ns/op   16 B/op   1 allocs/op

BenchmarkRWMutex_Single-8     100000000   12 ns/op    0 B/op   0 allocs/op
BenchmarkSyncMap_Single-8      50000000   28 ns/op    0 B/op   0 allocs/op
```

## 결과 해석

| 시나리오 | 추천 |
|---|---|
| **Read만** (100%) | RWMutex (sync.Map보다 빠름) |
| **Read 위주** (95%) | RWMutex (근소 차이지만 우위) |
| **혼합** (50/50) | sync.Map이 유리 |
| **단일 고루틴** | RWMutex (sync.Map은 오버헤드만 큼) |

### `sync.Map` 공식 권장 사용 케이스

`sync.Map` 공식 문서가 적시한 케이스는:
1. **한 번 쓰고 여러 번 읽는** 키들의 비중이 크다
2. **여러 고루틴이 서로 다른 키를** 동시에 다룬다

대부분의 일반 캐시에서는 **`map + RWMutex`가 더 단순하고 빠릅니다.** "당연히 sync.Map이 빠를 것"이라고 가정하지 말고 측정하세요.

---

# 복습 과제 ④ — Bounded worker pool

## 문제

최대 N개 작업만 동시에 실행하는 풀 — 세마포어 채널 패턴.

## 솔루션 — `bounded_pool.go`

```go
package main

import (
    "context"
    "fmt"
    "sync"
    "sync/atomic"
    "time"
)

// BoundedPool은 동시 실행 작업 수를 제한
type BoundedPool struct {
    sem chan struct{}
    wg  sync.WaitGroup

    // 통계
    submitted int64
    running   int64
    completed int64
}

func NewBoundedPool(maxConcurrent int) *BoundedPool {
    return &BoundedPool{
        sem: make(chan struct{}, maxConcurrent),
    }
}

// Submit은 작업을 풀에 제출. ctx가 만료되면 제출 자체가 실패할 수 있음.
func (p *BoundedPool) Submit(ctx context.Context, task func()) error {
    // 슬롯 획득
    select {
    case p.sem <- struct{}{}:
    case <-ctx.Done():
        return ctx.Err()
    }

    atomic.AddInt64(&p.submitted, 1)
    p.wg.Add(1)

    go func() {
        defer p.wg.Done()
        defer func() { <-p.sem }() // 슬롯 반환

        atomic.AddInt64(&p.running, 1)
        defer atomic.AddInt64(&p.running, -1)

        task()

        atomic.AddInt64(&p.completed, 1)
    }()

    return nil
}

// Wait는 모든 작업 완료까지 대기
func (p *BoundedPool) Wait() {
    p.wg.Wait()
}

// Stats는 현재 통계 반환
func (p *BoundedPool) Stats() (submitted, running, completed int64) {
    return atomic.LoadInt64(&p.submitted),
           atomic.LoadInt64(&p.running),
           atomic.LoadInt64(&p.completed)
}

// === 데모 ===
func main() {
    const maxConcurrent = 3
    pool := NewBoundedPool(maxConcurrent)

    ctx := context.Background()

    // 모니터
    monitorDone := make(chan struct{})
    go func() {
        ticker := time.NewTicker(200 * time.Millisecond)
        defer ticker.Stop()
        for {
            select {
            case <-monitorDone:
                return
            case <-ticker.C:
                s, r, c := pool.Stats()
                fmt.Printf("[모니터] 제출=%d 실행=%d 완료=%d\n", s, r, c)
            }
        }
    }()

    // 10개 작업 제출 (최대 3개만 동시 실행됨)
    for i := 1; i <= 10; i++ {
        i := i
        if err := pool.Submit(ctx, func() {
            fmt.Printf("  → 작업 %d 시작\n", i)
            time.Sleep(500 * time.Millisecond)
            fmt.Printf("  ← 작업 %d 완료\n", i)
        }); err != nil {
            fmt.Println("제출 실패:", err)
        }
    }

    pool.Wait()
    close(monitorDone)
    time.Sleep(100 * time.Millisecond)

    s, r, c := pool.Stats()
    fmt.Printf("\n최종: 제출=%d 실행=%d 완료=%d\n", s, r, c)
}
```

## 실행 결과

```
  → 작업 1 시작
  → 작업 2 시작
  → 작업 3 시작
[모니터] 제출=3 실행=3 완료=0
[모니터] 제출=3 실행=3 완료=0
  ← 작업 1 완료
  → 작업 4 시작
  ← 작업 2 완료
  → 작업 5 시작
  ← 작업 3 완료
  → 작업 6 시작
[모니터] 제출=6 실행=3 완료=3
...
최종: 제출=10 실행=0 완료=10
```

**동시에 최대 3개만 실행됨**을 확인할 수 있습니다.

## 활용 예 — HTTP 요청 동시 제한

```go
pool := NewBoundedPool(10) // API rate limit 대응

urls := []string{...}
for _, url := range urls {
    url := url
    pool.Submit(ctx, func() {
        resp, _ := http.Get(url)
        // 처리...
        resp.Body.Close()
    })
}
pool.Wait()
```

C에서 `pthread_pool` 직접 구현하던 일이 50줄로 해결됩니다.

---

# 도전 과제 ① — 메트릭 추가 (Producer/Consumer)

3일차 7교시 Producer-Consumer에 atomic 카운터로 메트릭 추가.

## 핵심 코드 — `metrics.go`

```go
package main

import (
    "sync/atomic"
    "time"
)

type Metrics struct {
    Produced  [3]int64  // ProducerID별 카운트 (3명)
    Consumed  [5]int64  // ConsumerID별 카운트 (5명)
    StartTime time.Time
}

func NewMetrics() *Metrics {
    return &Metrics{StartTime: time.Now()}
}

func (m *Metrics) IncProduced(id int) {
    atomic.AddInt64(&m.Produced[id-1], 1)
}

func (m *Metrics) IncConsumed(id int) {
    atomic.AddInt64(&m.Consumed[id-1], 1)
}

func (m *Metrics) Report() {
    elapsed := time.Since(m.StartTime).Seconds()

    fmt.Println("\n=== 메트릭 보고서 ===")
    fmt.Printf("총 실행 시간: %.2fs\n\n", elapsed)

    var totalProd, totalCons int64
    fmt.Println("Producers:")
    for i := range m.Produced {
        c := atomic.LoadInt64(&m.Produced[i])
        totalProd += c
        fmt.Printf("  P%d: %d개 (%.1f/s)\n", i+1, c, float64(c)/elapsed)
    }
    fmt.Printf("  total: %d (%.1f/s)\n\n", totalProd, float64(totalProd)/elapsed)

    fmt.Println("Consumers:")
    for i := range m.Consumed {
        c := atomic.LoadInt64(&m.Consumed[i])
        totalCons += c
        fmt.Printf("  C%d: %d개 (%.1f/s)\n", i+1, c, float64(c)/elapsed)
    }
    fmt.Printf("  total: %d (%.1f/s)\n", totalCons, float64(totalCons)/elapsed)

    if totalProd != totalCons {
        fmt.Printf("⚠️  미처리: %d개\n", totalProd-totalCons)
    }
}
```

## Producer/Consumer에 통합

```go
func producer(id int, out chan<- LogEntry, done <-chan struct{}, m *Metrics, wg *sync.WaitGroup) {
    defer wg.Done()
    // ... 기존 코드 ...
    for {
        // ... 송신 후 ...
        m.IncProduced(id)
    }
}

func consumer(id int, in <-chan LogEntry, m *Metrics, wg *sync.WaitGroup) {
    defer wg.Done()
    for entry := range in {
        // 처리...
        m.IncConsumed(id)
    }
}
```

`main`의 종료 시점에서 `metrics.Report()` 호출.

## 출력 예시

```
=== 메트릭 보고서 ===
총 실행 시간: 5.34s

Producers:
  P1: 53개 (9.9/s)
  P2: 48개 (9.0/s)
  P3: 51개 (9.6/s)
  total: 152 (28.5/s)

Consumers:
  C1: 31개 (5.8/s)
  C2: 30개 (5.6/s)
  C3: 31개 (5.8/s)
  C4: 30개 (5.6/s)
  C5: 30개 (5.6/s)
  total: 152 (28.5/s)
```

**각 워커의 처리 균등성**을 한눈에 볼 수 있습니다.

---

# 도전 과제 ② — 백프레셔 측정

## 문제

채널이 가득 차서 Producer가 블록된 시간 측정.

## 핵심 아이디어

`select` + non-blocking 송신을 먼저 시도하고, 실패하면 타임스탬프를 찍은 후 blocking 송신으로 전환.

## 솔루션

```go
type BackpressureMetrics struct {
    BlockedTime  int64 // nanoseconds (atomic)
    BlockedCount int64
}

func (m *BackpressureMetrics) AddBlock(d time.Duration) {
    atomic.AddInt64(&m.BlockedTime, int64(d))
    atomic.AddInt64(&m.BlockedCount, 1)
}

func producerWithBP(id int, out chan<- LogEntry, done <-chan struct{}, bp *BackpressureMetrics) {
    // ... 기존 코드 ...
    
    // 송신 시도 - 블록 시간 측정
    select {
    case out <- entry:
        // 즉시 성공 - 블록 없음
    default:
        // 채널이 가득 참 - 블록 측정 시작
        blockStart := time.Now()
        select {
        case out <- entry:
            bp.AddBlock(time.Since(blockStart))
        case <-done:
            return
        }
    }
}

func (m *BackpressureMetrics) Report() {
    blockedNs := atomic.LoadInt64(&m.BlockedTime)
    count := atomic.LoadInt64(&m.BlockedCount)
    if count == 0 {
        fmt.Println("\n백프레셔: 발생 없음 ✅")
        return
    }
    avg := time.Duration(blockedNs / count)
    total := time.Duration(blockedNs)
    fmt.Printf("\n백프레셔 보고:\n")
    fmt.Printf("  발생 횟수: %d\n", count)
    fmt.Printf("  총 블록 시간: %v\n", total)
    fmt.Printf("  평균 블록 시간: %v\n", avg)
}
```

## 활용

- 백프레셔가 자주 발생하면 → **Consumer 수 늘리기** 또는 **채널 버퍼 크기 늘리기**
- 발생이 거의 없으면 → **현재 설정이 적절**

이는 **운영 시 부하 튜닝의 핵심 메트릭**입니다.

---

# 도전 과제 ③ — Dynamic worker pool

## 문제

Consumer 개수를 런타임에 늘리고 줄일 수 있게.

## 핵심 아이디어

각 워커에 **개별 종료 채널**을 두고, 컨트롤러가 워커 추가/제거를 관리.

## 솔루션 — `dynamic_pool.go`

```go
package main

import (
    "fmt"
    "sync"
    "time"
)

type DynamicPool struct {
    mu       sync.Mutex
    jobs     <-chan int
    workers  map[int]chan struct{} // workerID → quit channel
    nextID   int
    wg       sync.WaitGroup
}

func NewDynamicPool(jobs <-chan int) *DynamicPool {
    return &DynamicPool{
        jobs:    jobs,
        workers: make(map[int]chan struct{}),
        nextID:  1,
    }
}

// AddWorker는 새 워커를 추가
func (p *DynamicPool) AddWorker() int {
    p.mu.Lock()
    defer p.mu.Unlock()

    id := p.nextID
    p.nextID++

    quit := make(chan struct{})
    p.workers[id] = quit

    p.wg.Add(1)
    go p.workerLoop(id, quit)

    fmt.Printf("[Pool] 워커 %d 추가 (총 %d명)\n", id, len(p.workers))
    return id
}

// RemoveWorker는 가장 최근 워커를 제거
func (p *DynamicPool) RemoveWorker() {
    p.mu.Lock()
    defer p.mu.Unlock()

    if len(p.workers) == 0 {
        return
    }

    // 가장 큰 ID 찾기
    var lastID int
    for id := range p.workers {
        if id > lastID {
            lastID = id
        }
    }

    close(p.workers[lastID])
    delete(p.workers, lastID)
    fmt.Printf("[Pool] 워커 %d 제거 (총 %d명)\n", lastID, len(p.workers))
}

// Wait는 모든 워커 종료 대기
func (p *DynamicPool) Wait() {
    p.wg.Wait()
}

// CloseAll은 모든 워커 종료
func (p *DynamicPool) CloseAll() {
    p.mu.Lock()
    defer p.mu.Unlock()
    for id, quit := range p.workers {
        close(quit)
        delete(p.workers, id)
    }
}

func (p *DynamicPool) workerLoop(id int, quit <-chan struct{}) {
    defer p.wg.Done()
    defer fmt.Printf("[Worker %d] 종료\n", id)

    for {
        select {
        case <-quit:
            return
        case job, ok := <-p.jobs:
            if !ok {
                return
            }
            fmt.Printf("[Worker %d] 작업 %d 처리\n", id, job)
            time.Sleep(200 * time.Millisecond)
        }
    }
}

// === 데모 ===
func main() {
    jobs := make(chan int)
    pool := NewDynamicPool(jobs)

    // 시작: 워커 2명
    pool.AddWorker()
    pool.AddWorker()

    // 작업 송신
    go func() {
        defer close(jobs)
        for i := 1; i <= 20; i++ {
            jobs <- i
        }
    }()

    // 1.5초 후 워커 추가
    time.Sleep(1500 * time.Millisecond)
    pool.AddWorker()
    pool.AddWorker()

    // 다시 1.5초 후 워커 감축
    time.Sleep(1500 * time.Millisecond)
    pool.RemoveWorker()

    pool.Wait()
    fmt.Println("모든 작업 완료")
}
```

## 실행 결과 예시

```
[Pool] 워커 1 추가 (총 1명)
[Pool] 워커 2 추가 (총 2명)
[Worker 1] 작업 1 처리
[Worker 2] 작업 2 처리
[Worker 1] 작업 3 처리
...
[Pool] 워커 3 추가 (총 3명)
[Pool] 워커 4 추가 (총 4명)
[Worker 3] 작업 11 처리
[Worker 4] 작업 12 처리
...
[Pool] 워커 4 제거 (총 3명)
[Worker 4] 종료
...
모든 작업 완료
```

## 활용 예 — 부하에 따라 자동 스케일링

```go
// 큐 길이를 보고 워커 조절
for {
    queueLen := len(jobs)
    if queueLen > 100 && currentWorkers < maxWorkers {
        pool.AddWorker()
    } else if queueLen < 10 && currentWorkers > minWorkers {
        pool.RemoveWorker()
    }
    time.Sleep(time.Second)
}
```

이는 Kubernetes HPA(Horizontal Pod Autoscaler)와 유사한 사고방식입니다.

---

# 도전 과제 ④ — Priority queue

## 문제

LogEntry에 우선순위 필드를 두고, 높은 우선순위가 먼저 처리되도록.

## 핵심 — `container/heap` 활용

Go 표준 라이브러리의 `container/heap`을 사용합니다. C의 STL과 같은 우선순위 큐 구현체.

## 솔루션 — `priority_queue.go`

```go
package main

import (
    "container/heap"
    "fmt"
    "sync"
    "time"
)

type Priority int

const (
    Low Priority = iota
    Normal
    High
    Critical
)

type PriorityEntry struct {
    Priority Priority
    Message  string
    AddedAt  time.Time
    index    int // heap 인덱스
}

// === heap.Interface 구현 ===

type PriorityQueue []*PriorityEntry

func (pq PriorityQueue) Len() int { return len(pq) }

func (pq PriorityQueue) Less(i, j int) bool {
    // 우선순위가 높은 게 먼저 (max-heap)
    if pq[i].Priority != pq[j].Priority {
        return pq[i].Priority > pq[j].Priority
    }
    // 같으면 먼저 들어온 게 먼저 (FIFO)
    return pq[i].AddedAt.Before(pq[j].AddedAt)
}

func (pq PriorityQueue) Swap(i, j int) {
    pq[i], pq[j] = pq[j], pq[i]
    pq[i].index = i
    pq[j].index = j
}

func (pq *PriorityQueue) Push(x any) {
    n := len(*pq)
    item := x.(*PriorityEntry)
    item.index = n
    *pq = append(*pq, item)
}

func (pq *PriorityQueue) Pop() any {
    old := *pq
    n := len(old)
    item := old[n-1]
    old[n-1] = nil
    item.index = -1
    *pq = old[:n-1]
    return item
}

// === 동시성 안전 wrapper ===

type ConcurrentPQ struct {
    mu   sync.Mutex
    pq   PriorityQueue
    cond *sync.Cond
    closed bool
}

func NewConcurrentPQ() *ConcurrentPQ {
    cpq := &ConcurrentPQ{pq: make(PriorityQueue, 0)}
    cpq.cond = sync.NewCond(&cpq.mu)
    heap.Init(&cpq.pq)
    return cpq
}

func (c *ConcurrentPQ) Push(e *PriorityEntry) {
    c.mu.Lock()
    defer c.mu.Unlock()
    heap.Push(&c.pq, e)
    c.cond.Signal()
}

// Pop은 우선순위가 가장 높은 항목 반환 (블로킹)
func (c *ConcurrentPQ) Pop() (*PriorityEntry, bool) {
    c.mu.Lock()
    defer c.mu.Unlock()
    for len(c.pq) == 0 && !c.closed {
        c.cond.Wait()
    }
    if c.closed && len(c.pq) == 0 {
        return nil, false
    }
    return heap.Pop(&c.pq).(*PriorityEntry), true
}

func (c *ConcurrentPQ) Close() {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.closed = true
    c.cond.Broadcast()
}

// === 데모 ===
func main() {
    pq := NewConcurrentPQ()

    // Producer
    var wgP sync.WaitGroup
    wgP.Add(1)
    go func() {
        defer wgP.Done()
        items := []struct {
            p Priority
            m string
        }{
            {Low, "로우 작업 A"},
            {High, "하이 작업 1"},
            {Normal, "노멀 작업 X"},
            {Critical, "🚨 크리티컬 1"},
            {Low, "로우 작업 B"},
            {High, "하이 작업 2"},
            {Critical, "🚨 크리티컬 2"},
        }
        for _, it := range items {
            pq.Push(&PriorityEntry{
                Priority: it.p,
                Message:  it.m,
                AddedAt:  time.Now(),
            })
            time.Sleep(50 * time.Millisecond)
        }
        time.Sleep(200 * time.Millisecond)
        pq.Close()
    }()

    // Consumer
    var wgC sync.WaitGroup
    wgC.Add(1)
    go func() {
        defer wgC.Done()
        for {
            e, ok := pq.Pop()
            if !ok {
                return
            }
            fmt.Printf("처리: [%s] %s\n", levelName(e.Priority), e.Message)
            time.Sleep(150 * time.Millisecond)
        }
    }()

    wgP.Wait()
    wgC.Wait()
}

func levelName(p Priority) string {
    switch p {
    case Low:      return "LOW"
    case Normal:   return "NORMAL"
    case High:     return "HIGH"
    case Critical: return "CRIT"
    }
    return "?"
}
```

## 실행 결과

```
처리: [LOW] 로우 작업 A
처리: [CRIT] 🚨 크리티컬 1
처리: [HIGH] 하이 작업 1
처리: [HIGH] 하이 작업 2
처리: [CRIT] 🚨 크리티컬 2
처리: [NORMAL] 노멀 작업 X
처리: [LOW] 로우 작업 B
```

(소비 속도가 생산보다 느려서, 큐에 쌓인 순간 우선순위로 재정렬됨)

**핵심**: 처리 시점에 큐에 있는 항목 중 가장 우선순위가 높은 게 선택됨.

## 학습 포인트

| 요소 | 역할 |
|---|---|
| `heap.Interface` | `Len`, `Less`, `Swap`, `Push`, `Pop` 5개 메서드 |
| `sync.Mutex + Cond` | 빈 큐 대기 처리 (5교시 sync.Cond 활용) |
| `Broadcast` | 종료 시 모든 대기자 깨우기 |

C에서 `priority_queue`를 직접 구현하면 200줄 이상의 코드가 필요하지만, Go는 `container/heap` 인터페이스만 구현하면 됩니다.

---

# 🎯 3일차 솔루션 마무리

| 솔루션 | 핵심 학습 |
|---|---|
| 누수 탐지기 | `runtime.NumGoroutine`, 모니터 패턴 |
| Fan-out/Fan-in | 워커 수에 따른 가속 확인 |
| RWMutex vs sync.Map | 벤치마크 기반 의사결정 |
| Bounded pool | 세마포어 채널, atomic 카운터 |
| 메트릭 | `sync/atomic`으로 안전한 카운터 |
| 백프레셔 | non-blocking 송신 + 시간 측정 |
| Dynamic pool | 개별 quit 채널, 런타임 워커 조절 |
| Priority queue | `container/heap` + `sync.Cond` |

다음은 [4일차 솔루션](./Go언어프로그래밍_4일차_솔루션.md)으로 이어집니다.
