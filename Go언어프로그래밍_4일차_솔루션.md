# Go 4일차 — 도전 과제 및 복습 과제 솔루션

> 4일차 강의 자료의 도전 과제(healthcheck/로그분석 확장)와 복습 과제(Web Scraper, Rate Limiter, Context Tree, 제네릭 파이프라인) 솔루션입니다.

---

## 📑 목차

| 구분 | 과제 | 난이도 |
|---|---|---|
| 복습 ① | Web Scraper 미니 프로젝트 | ⭐⭐⭐ |
| 복습 ② | Rate Limiter (`time.Ticker`) | ⭐⭐ |
| 복습 ③ | Context Tree Visualizer | ⭐⭐⭐ |
| 복습 ④ | 제네릭 Pipeline 헬퍼 | ⭐⭐⭐⭐ |
| 도전 ① | 헬스체커 — 재시도 + 지수 백오프 | ⭐⭐ |
| 도전 ② | 헬스체커 — JSON 출력 | ⭐ |
| 도전 ③ | 헬스체커 — 응답시간 통계 (p50/p95/p99) | ⭐⭐⭐ |
| 도전 ④ | 헬스체커 — Rate Limit | ⭐⭐ |
| 도전 ⑤ | 로그 분석 — 에러 채널 분리 | ⭐⭐ |

---

# 복습 과제 ① — Web Scraper 미니 프로젝트

## 문제

URL 목록을 받아 페이지 제목을 추출하는 도구. Worker Pool + ctx + 재시도 로직 포함.

## 솔루션 — `scraper.go`

```go
package main

import (
    "context"
    "errors"
    "fmt"
    "io"
    "net/http"
    "os"
    "regexp"
    "strings"
    "sync"
    "time"
)

type ScrapeResult struct {
    URL     string
    Title   string
    Attempts int
    Latency time.Duration
    Err     error
}

func (r ScrapeResult) String() string {
    if r.Err != nil {
        return fmt.Sprintf("❌ %s (시도 %d회): %v", r.URL, r.Attempts, r.Err)
    }
    return fmt.Sprintf("✅ %s → %q (%v, 시도 %d회)",
        r.URL, r.Title, r.Latency, r.Attempts)
}

var titleRe = regexp.MustCompile(`(?i)<title[^>]*>([^<]+)</title>`)

// 단일 페이지 스크래핑 (재시도 미포함)
func scrapeOnce(ctx context.Context, url string) (string, error) {
    req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
    if err != nil {
        return "", err
    }
    req.Header.Set("User-Agent", "Mozilla/5.0 (compatible; goscraper/1.0)")

    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        return "", err
    }
    defer resp.Body.Close()

    if resp.StatusCode != http.StatusOK {
        return "", fmt.Errorf("HTTP %d", resp.StatusCode)
    }

    body, err := io.ReadAll(io.LimitReader(resp.Body, 1024*1024)) // 1MB 제한
    if err != nil {
        return "", err
    }

    m := titleRe.FindSubmatch(body)
    if m == nil {
        return "", errors.New("<title> 태그 없음")
    }
    return strings.TrimSpace(string(m[1])), nil
}

// 재시도 포함 스크래핑 — 지수 백오프
func scrapeWithRetry(ctx context.Context, url string, maxRetries int) ScrapeResult {
    var (
        result ScrapeResult
        delay  = 200 * time.Millisecond
    )
    result.URL = url

    for attempt := 1; attempt <= maxRetries; attempt++ {
        result.Attempts = attempt
        start := time.Now()

        title, err := scrapeOnce(ctx, url)
        result.Latency = time.Since(start)

        if err == nil {
            result.Title = title
            return result
        }
        result.Err = err

        // 마지막 시도였으면 그대로 종료
        if attempt == maxRetries {
            return result
        }

        // 컨텍스트가 취소되면 즉시 종료
        select {
        case <-ctx.Done():
            return result
        case <-time.After(delay):
        }
        delay *= 2 // 지수 백오프
    }
    return result
}

// 워커 풀 기반 스크래핑
func scrapeAll(ctx context.Context, urls []string, workers, maxRetries int) []ScrapeResult {
    jobs := make(chan string)
    results := make(chan ScrapeResult, len(urls))

    var wg sync.WaitGroup
    for w := 0; w < workers; w++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            for url := range jobs {
                results <- scrapeWithRetry(ctx, url, maxRetries)
            }
        }()
    }

    // 작업 송신
    go func() {
        defer close(jobs)
        for _, u := range urls {
            select {
            case jobs <- u:
            case <-ctx.Done():
                return
            }
        }
    }()

    // 결과 수집
    go func() {
        wg.Wait()
        close(results)
    }()

    out := make([]ScrapeResult, 0, len(urls))
    for r := range results {
        out = append(out, r)
    }
    return out
}

func main() {
    urls := []string{
        "https://go.dev",
        "https://github.com",
        "https://example.com",
        "https://invalid-foo-bar-baz.test", // 실패 사례
    }

    ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
    defer cancel()

    results := scrapeAll(ctx, urls, 3, 3)
    for _, r := range results {
        fmt.Fprintln(os.Stdout, r)
    }
}
```

## 실행 결과

```
✅ https://example.com → "Example Domain" (245ms, 시도 1회)
✅ https://go.dev → "The Go Programming Language" (380ms, 시도 1회)
✅ https://github.com → "GitHub: Let's build from here" (412ms, 시도 1회)
❌ https://invalid-foo-bar-baz.test (시도 3회): Get ...: dial tcp: lookup invalid-foo-bar-baz.test: no such host
```

## 학습 포인트

| 요소 | 활용 |
|---|---|
| `context.WithTimeout` | 전체 작업 데드라인 |
| `http.NewRequestWithContext` | 요청 단위 취소 |
| 지수 백오프 | `delay *= 2` |
| `io.LimitReader` | 메모리 폭증 방지 |
| Worker Pool | `chan string` + `for range` |

## 변형 — Atomic 진행률 표시

```go
var processed int64
// 워커 내부에서
atomic.AddInt64(&processed, 1)

// 별도 고루틴에서
go func() {
    for {
        select {
        case <-ctx.Done():
            return
        case <-time.After(time.Second):
            done := atomic.LoadInt64(&processed)
            fmt.Fprintf(os.Stderr, "진행: %d/%d\n", done, len(urls))
        }
    }
}()
```

---

# 복습 과제 ② — Rate Limiter

## 문제

`time.Ticker`로 초당 N개로 호출 제한하는 헬퍼.

## 솔루션 — `rate_limit.go`

```go
package main

import (
    "context"
    "fmt"
    "sync"
    "time"
)

// RateLimiter는 초당 maxRate개까지 허용
type RateLimiter struct {
    interval time.Duration
    bucket   chan struct{}
    stop     chan struct{}
    once     sync.Once
}

func NewRateLimiter(perSecond int) *RateLimiter {
    if perSecond <= 0 {
        perSecond = 1
    }
    rl := &RateLimiter{
        interval: time.Second / time.Duration(perSecond),
        bucket:   make(chan struct{}, perSecond), // burst 허용
        stop:     make(chan struct{}),
    }
    // 초기 버킷 채우기 (burst)
    for i := 0; i < perSecond; i++ {
        rl.bucket <- struct{}{}
    }
    go rl.refill()
    return rl
}

func (rl *RateLimiter) refill() {
    ticker := time.NewTicker(rl.interval)
    defer ticker.Stop()
    for {
        select {
        case <-rl.stop:
            return
        case <-ticker.C:
            select {
            case rl.bucket <- struct{}{}:
            default:
                // 버킷 가득 - 그냥 무시
            }
        }
    }
}

// Wait는 토큰이 생길 때까지 대기 (ctx 만료 시 에러)
func (rl *RateLimiter) Wait(ctx context.Context) error {
    select {
    case <-rl.bucket:
        return nil
    case <-ctx.Done():
        return ctx.Err()
    }
}

// Allow는 즉시 토큰 시도 (non-blocking)
func (rl *RateLimiter) Allow() bool {
    select {
    case <-rl.bucket:
        return true
    default:
        return false
    }
}

func (rl *RateLimiter) Stop() {
    rl.once.Do(func() { close(rl.stop) })
}

// === 데모 ===
func main() {
    rl := NewRateLimiter(3) // 초당 3개
    defer rl.Stop()

    ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
    defer cancel()

    start := time.Now()
    for i := 1; i <= 10; i++ {
        if err := rl.Wait(ctx); err != nil {
            fmt.Println("취소됨:", err)
            return
        }
        fmt.Printf("[%v] 요청 %d 처리\n", time.Since(start).Truncate(time.Millisecond), i)
    }
}
```

## 실행 결과

```
[0s] 요청 1 처리
[0s] 요청 2 처리
[0s] 요청 3 처리         ← 초기 burst 3개 즉시
[333ms] 요청 4 처리      ← 333ms마다 리필
[666ms] 요청 5 처리
[1s] 요청 6 처리
[1.333s] 요청 7 처리
[1.666s] 요청 8 처리
[2s] 요청 9 처리
[2.333s] 요청 10 처리
```

10개 요청을 약 2.3초에 걸쳐 처리 — **초당 3개 이내 보장**.

## 토큰 버킷 알고리즘

이 구현은 **token bucket** 알고리즘입니다.

- **버킷**: 토큰을 담는 컨테이너 (채널 buffer)
- **리필**: 일정 주기로 토큰 추가 (ticker)
- **소비**: 요청마다 토큰 1개 소비
- **버스트**: 버킷 가득 차면 일시적 폭증 허용

## 변형 — golang.org/x/time/rate (표준 추천)

실무에서는 보통 표준 보조 패키지를 씁니다.

```bash
go get golang.org/x/time/rate
```

```go
import "golang.org/x/time/rate"

limiter := rate.NewLimiter(rate.Limit(3), 5) // 초당 3개, burst 5
if err := limiter.Wait(ctx); err != nil {
    return err
}
// 호출
```

직접 구현 vs 라이브러리는 학습 목적이면 직접, 운영 환경이면 라이브러리를 권장합니다.

---

# 복습 과제 ③ — Context Tree Visualizer

## 문제

`WithCancel`/`WithTimeout`을 중첩해 만들고, 어떤 시점에 어디가 취소되는지 추적.

## 솔루션 — `ctx_tree.go`

```go
package main

import (
    "context"
    "fmt"
    "sync"
    "time"
)

type CtxNode struct {
    Name     string
    Ctx      context.Context
    cancel   context.CancelFunc
    Children []*CtxNode
    Created  time.Time
}

func NewRoot(name string) *CtxNode {
    ctx, cancel := context.WithCancel(context.Background())
    return &CtxNode{
        Name:    name,
        Ctx:     ctx,
        cancel:  cancel,
        Created: time.Now(),
    }
}

func (n *CtxNode) Branch(name string) *CtxNode {
    ctx, cancel := context.WithCancel(n.Ctx)
    child := &CtxNode{
        Name:    name,
        Ctx:     ctx,
        cancel:  cancel,
        Created: time.Now(),
    }
    n.Children = append(n.Children, child)
    return child
}

func (n *CtxNode) BranchTimeout(name string, d time.Duration) *CtxNode {
    ctx, cancel := context.WithTimeout(n.Ctx, d)
    child := &CtxNode{
        Name:    name,
        Ctx:     ctx,
        cancel:  cancel,
        Created: time.Now(),
    }
    n.Children = append(n.Children, child)
    return child
}

func (n *CtxNode) Cancel() {
    n.cancel()
}

// 모니터: 각 노드의 종료 시점 로깅
func monitor(n *CtxNode, base time.Time, mu *sync.Mutex, indent int) {
    go func() {
        <-n.Ctx.Done()
        mu.Lock()
        fmt.Printf("%s[%-7v] %s 취소됨: %v\n",
            strings.Repeat("  ", indent),
            time.Since(base).Truncate(time.Millisecond),
            n.Name,
            n.Ctx.Err())
        mu.Unlock()
    }()
    for _, c := range n.Children {
        monitor(c, base, mu, indent+1)
    }
}

// 트리 구조 시각화
func (n *CtxNode) Print(indent int) {
    fmt.Printf("%s├─ %s\n", strings.Repeat("  ", indent), n.Name)
    for _, c := range n.Children {
        c.Print(indent + 1)
    }
}

// import strings 추가 필요
```

## 데모

```go
import "strings"

func main() {
    base := time.Now()
    var mu sync.Mutex

    // 트리 구성
    root := NewRoot("root")
    api := root.Branch("API")
    db := api.BranchTimeout("DB(1s)", 1*time.Second)
    cache := api.BranchTimeout("Cache(500ms)", 500*time.Millisecond)

    worker := root.BranchTimeout("Worker(3s)", 3*time.Second)
    worker.Branch("WorkerChild1")
    worker.Branch("WorkerChild2")

    // 트리 구조 출력
    fmt.Println("=== Context Tree ===")
    root.Print(0)
    fmt.Println()

    // 모니터링 시작
    monitor(root, base, &mu, 0)

    // 시나리오:
    // 1. 500ms 후: Cache 자동 만료
    // 2. 1s 후: DB 자동 만료
    // 3. 1.5s 후: API 수동 취소 → API 하위 모두 영향 없음 (이미 만료)
    // 4. 3s 후: Worker 자동 만료 (하위 자식들도 동시에)
    time.Sleep(1500 * time.Millisecond)
    fmt.Printf("[%-7v] API 수동 cancel 호출\n",
        time.Since(base).Truncate(time.Millisecond))
    api.Cancel()

    time.Sleep(2 * time.Second)
    fmt.Println("\n=== 종료 ===")
}
```

## 실행 결과

```
=== Context Tree ===
├─ root
  ├─ API
    ├─ DB(1s)
    ├─ Cache(500ms)
  ├─ Worker(3s)
    ├─ WorkerChild1
    ├─ WorkerChild2

      [500ms ] Cache(500ms) 취소됨: context deadline exceeded
      [1s    ] DB(1s) 취소됨: context deadline exceeded
[1.5s ] API 수동 cancel 호출
    [1.5s ] API 취소됨: context canceled
      [3s    ] Worker(3s) 취소됨: context deadline exceeded
        [3s    ] WorkerChild1 취소됨: context canceled
        [3s    ] WorkerChild2 취소됨: context canceled

=== 종료 ===
```

**관찰 포인트**:
- 짧은 타임아웃이 먼저 만료 (Cache → DB)
- 수동 cancel 전파 (API 취소 시 자식들은 이미 만료)
- Worker 만료 시 자식들도 **동시에 자동 취소** (전파!)

## 학습 포인트

| 패턴 | 의미 |
|---|---|
| 트리 구조 | Context 전파 방향성 |
| 짧은 데드라인 우선 | 부모보다 자식이 일찍 만료 가능 |
| 부모 취소 → 자식 자동 취소 | 명시적 cancel 불필요 |
| 시간 측정 | 어디가 언제 끝났는지 추적 |

---

# 복습 과제 ④ — 제네릭 Pipeline 헬퍼

## 문제

임의 타입의 데이터 파이프라인을 만들기 위한 제네릭 헬퍼.

`func Stage[In, Out any](fn func(In) Out) func(<-chan In) <-chan Out`

## 솔루션 — `pipeline_generic.go`

```go
package main

import (
    "context"
    "fmt"
    "strings"
    "sync"
)

// === 제네릭 파이프라인 헬퍼 ===

// Source: 슬라이스로부터 채널 생성
func Source[T any](ctx context.Context, items []T) <-chan T {
    out := make(chan T)
    go func() {
        defer close(out)
        for _, v := range items {
            select {
            case out <- v:
            case <-ctx.Done():
                return
            }
        }
    }()
    return out
}

// Stage: 1:1 변환 단계
func Stage[In, Out any](ctx context.Context, in <-chan In, fn func(In) Out) <-chan Out {
    out := make(chan Out)
    go func() {
        defer close(out)
        for v := range in {
            result := fn(v)
            select {
            case out <- result:
            case <-ctx.Done():
                return
            }
        }
    }()
    return out
}

// Filter: 조건 충족하는 항목만 통과
func Filter[T any](ctx context.Context, in <-chan T, pred func(T) bool) <-chan T {
    out := make(chan T)
    go func() {
        defer close(out)
        for v := range in {
            if !pred(v) {
                continue
            }
            select {
            case out <- v:
            case <-ctx.Done():
                return
            }
        }
    }()
    return out
}

// FanOut: 입력을 N개 채널로 동일 송신 (각 항목은 한 채널만 받음)
func FanOut[T any](ctx context.Context, in <-chan T, n int) []<-chan T {
    outs := make([]chan T, n)
    for i := range outs {
        outs[i] = make(chan T)
    }

    go func() {
        // 모든 출력 채널을 끝에서 닫기
        defer func() {
            for _, c := range outs {
                close(c)
            }
        }()

        i := 0
        for v := range in {
            select {
            case outs[i] <- v:
            case <-ctx.Done():
                return
            }
            i = (i + 1) % n
        }
    }()

    // <-chan T 슬라이스로 변환
    ret := make([]<-chan T, n)
    for i, c := range outs {
        ret[i] = c
    }
    return ret
}

// FanIn: 여러 채널을 하나로 합치기
func FanIn[T any](ctx context.Context, ins ...<-chan T) <-chan T {
    out := make(chan T)
    var wg sync.WaitGroup

    for _, in := range ins {
        wg.Add(1)
        go func(c <-chan T) {
            defer wg.Done()
            for v := range c {
                select {
                case out <- v:
                case <-ctx.Done():
                    return
                }
            }
        }(in)
    }

    go func() {
        wg.Wait()
        close(out)
    }()
    return out
}

// Sink: 채널을 슬라이스로 수집
func Sink[T any](in <-chan T) []T {
    out := make([]T, 0)
    for v := range in {
        out = append(out, v)
    }
    return out
}

// === 데모 ===
func main() {
    ctx := context.Background()

    // 예제 1: 정수 → 제곱 → 짝수 필터 → 합
    nums := []int{1, 2, 3, 4, 5, 6, 7, 8, 9, 10}
    src := Source(ctx, nums)
    squared := Stage(ctx, src, func(n int) int { return n * n })
    even := Filter(ctx, squared, func(n int) bool { return n%2 == 0 })
    result := Sink(even)
    fmt.Println("짝수 제곱:", result) // [4 16 36 64 100]

    // 예제 2: 문자열 → 대문자화 (Fan-out + Fan-in)
    words := []string{"hello", "world", "go", "is", "fun", "and", "powerful", "language"}
    src2 := Source(ctx, words)
    parts := FanOut(ctx, src2, 3) // 3개 워커로 분배

    // 각 워커가 변환
    transformed := make([]<-chan string, 3)
    for i, p := range parts {
        transformed[i] = Stage(ctx, p, strings.ToUpper)
    }

    merged := FanIn(ctx, transformed...)
    upperResults := Sink(merged)
    fmt.Println("대문자:", upperResults)

    // 예제 3: 타입 변환 - int → string
    src3 := Source(ctx, []int{100, 200, 300})
    asStr := Stage(ctx, src3, func(n int) string {
        return fmt.Sprintf("값:%d", n)
    })
    fmt.Println("변환:", Sink(asStr))
}
```

## 실행 결과

```
짝수 제곱: [4 16 36 64 100]
대문자: [HELLO GO FUN POWERFUL WORLD IS AND LANGUAGE]  (순서는 다를 수 있음)
변환: [값:100 값:200 값:300]
```

## 학습 포인트

| 요소 | 효과 |
|---|---|
| `[T any]` | 모든 타입 지원 |
| `[In, Out any]` | 입출력 타입 분리 (`Stage`) |
| ctx 통합 | 모든 단계가 동시에 취소 가능 |
| `FanOut`이 round-robin | 부하 분산 (간단한 방식) |

## 변형 — 함수 합성

함수형 스타일을 좋아한다면:

```go
type StageFunc[In, Out any] func(<-chan In) <-chan Out

func Compose[A, B, C any](
    s1 StageFunc[A, B],
    s2 StageFunc[B, C],
) StageFunc[A, C] {
    return func(in <-chan A) <-chan C {
        return s2(s1(in))
    }
}
```

다만 Go는 함수형 언어가 아니어서 **명시적 단계 조합이 더 읽기 쉽습니다**. 위의 평면적 구조를 권장합니다.

---

# 도전 과제 ① — 헬스체커 재시도 + 지수 백오프

4일차 7교시 healthcheck에 재시도 로직 추가.

## `internal/checker/checker.go` 수정

```go
type RetryConfig struct {
    MaxAttempts int
    InitialDelay time.Duration
}

var DefaultRetry = RetryConfig{
    MaxAttempts:  3,
    InitialDelay: 200 * time.Millisecond,
}

// CheckWithRetry는 실패 시 지수 백오프로 재시도
func CheckWithRetry(ctx context.Context, url string, cfg RetryConfig) Result {
    var result Result
    delay := cfg.InitialDelay

    for attempt := 1; attempt <= cfg.MaxAttempts; attempt++ {
        result = Check(ctx, url)
        result.Attempts = attempt

        // 성공
        if result.Err == nil {
            return result
        }

        // 4xx는 재시도 의미 없음
        if result.StatusCode >= 400 && result.StatusCode < 500 {
            return result
        }

        // 마지막 시도였으면 종료
        if attempt == cfg.MaxAttempts {
            return result
        }

        // 백오프 대기
        select {
        case <-time.After(delay):
        case <-ctx.Done():
            result.Err = ctx.Err()
            return result
        }
        delay *= 2
    }
    return result
}
```

`Result` 구조체에 `Attempts int` 필드 추가.

## Pool에서 호출 변경

```go
func (p *Pool) workerLoop(ctx context.Context, id int) {
    for {
        select {
        case <-ctx.Done():
            return
        case t, ok := <-p.targets:
            if !ok {
                return
            }
            r := CheckWithRetry(ctx, t.URL, DefaultRetry)
            // ... 결과 처리
        }
    }
}
```

## 출력 변경

```
✅ https://go.dev — 200 (380ms, 시도 1회)
❌ https://flaky.example.com — 에러: ... (시도 3회)
```

---

# 도전 과제 ② — 헬스체커 JSON 출력

## `cmd/healthcheck/main.go` 수정

```go
var (
    workers   = flag.Int("w", 5, "동시 워커 수")
    timeout   = flag.Duration("t", 30*time.Second, "전체 타임아웃")
    jsonOut   = flag.Bool("json", false, "JSON 형식 출력")
)
```

JSON 출력용 구조체:

```go
type JSONOutput struct {
    Results []JSONResult `json:"results"`
    Summary JSONSummary  `json:"summary"`
}

type JSONResult struct {
    URL        string `json:"url"`
    StatusCode int    `json:"status_code,omitempty"`
    LatencyMs  int64  `json:"latency_ms,omitempty"`
    Error      string `json:"error,omitempty"`
    Attempts   int    `json:"attempts"`
}

type JSONSummary struct {
    Total     int `json:"total"`
    Succeeded int `json:"succeeded"`
    Failed    int `json:"failed"`
}
```

결과 수집 후:

```go
if *jsonOut {
    var out JSONOutput
    for _, r := range allResults {
        jr := JSONResult{
            URL:      r.URL,
            Attempts: r.Attempts,
        }
        if r.Err != nil {
            jr.Error = r.Err.Error()
            out.Summary.Failed++
        } else {
            jr.StatusCode = r.StatusCode
            jr.LatencyMs = r.Latency.Milliseconds()
            out.Summary.Succeeded++
        }
        out.Results = append(out.Results, jr)
    }
    out.Summary.Total = len(allResults)
    json.NewEncoder(os.Stdout).Encode(out)
} else {
    for _, r := range allResults {
        fmt.Println(r)
    }
}
```

## 실행

```bash
./bin/healthcheck -json https://go.dev https://example.com | jq
```

```json
{
  "results": [
    {
      "url": "https://go.dev",
      "status_code": 200,
      "latency_ms": 380,
      "attempts": 1
    },
    {
      "url": "https://example.com",
      "status_code": 200,
      "latency_ms": 245,
      "attempts": 1
    }
  ],
  "summary": {
    "total": 2,
    "succeeded": 2,
    "failed": 0
  }
}
```

CI나 모니터링 시스템과 통합하기 좋은 형식입니다.

---

# 도전 과제 ③ — 응답시간 통계 (p50/p95/p99)

## `internal/checker/stats.go` (새 파일)

```go
package checker

import (
    "math"
    "sort"
    "time"
)

type Percentiles struct {
    P50  time.Duration
    P95  time.Duration
    P99  time.Duration
    Min  time.Duration
    Max  time.Duration
    Mean time.Duration
}

func Calculate(latencies []time.Duration) Percentiles {
    if len(latencies) == 0 {
        return Percentiles{}
    }
    sorted := make([]time.Duration, len(latencies))
    copy(sorted, latencies)
    sort.Slice(sorted, func(i, j int) bool { return sorted[i] < sorted[j] })

    var sum time.Duration
    for _, l := range sorted {
        sum += l
    }

    return Percentiles{
        P50:  percentile(sorted, 0.50),
        P95:  percentile(sorted, 0.95),
        P99:  percentile(sorted, 0.99),
        Min:  sorted[0],
        Max:  sorted[len(sorted)-1],
        Mean: sum / time.Duration(len(sorted)),
    }
}

func percentile(sorted []time.Duration, p float64) time.Duration {
    if len(sorted) == 0 {
        return 0
    }
    if p <= 0 {
        return sorted[0]
    }
    if p >= 1 {
        return sorted[len(sorted)-1]
    }
    idx := int(math.Ceil(p*float64(len(sorted)))) - 1
    if idx < 0 {
        idx = 0
    }
    return sorted[idx]
}
```

## `cmd/healthcheck/main.go` 마지막에 추가

```go
// 성공한 요청들의 레이턴시만 수집
latencies := make([]time.Duration, 0)
for _, r := range allResults {
    if r.Err == nil {
        latencies = append(latencies, r.Latency)
    }
}

if len(latencies) > 0 {
    p := checker.Calculate(latencies)
    fmt.Printf("\n=== 응답 시간 통계 ===\n")
    fmt.Printf("  Min:  %v\n", p.Min)
    fmt.Printf("  P50:  %v\n", p.P50)
    fmt.Printf("  Mean: %v\n", p.Mean)
    fmt.Printf("  P95:  %v\n", p.P95)
    fmt.Printf("  P99:  %v\n", p.P99)
    fmt.Printf("  Max:  %v\n", p.Max)
}
```

## 단위 테스트

```go
func TestPercentile(t *testing.T) {
    latencies := []time.Duration{
        100 * time.Millisecond,
        200 * time.Millisecond,
        300 * time.Millisecond,
        400 * time.Millisecond,
        500 * time.Millisecond,
        // ... 100개라고 가정
    }
    p := Calculate(latencies)

    // 정확한 위치 검증은 데이터 분포에 따라
    if p.P50 < 100*time.Millisecond || p.P50 > 500*time.Millisecond {
        t.Errorf("P50 out of range: %v", p.P50)
    }
}
```

## 출력 예시

```
✅ https://go.dev — 200 (380ms, 시도 1회)
✅ https://github.com — 200 (412ms, 시도 1회)
...

=== 응답 시간 통계 ===
  Min:  120ms
  P50:  245ms
  Mean: 287ms
  P95:  450ms
  P99:  520ms
  Max:  580ms
```

**P99**가 P50보다 훨씬 크다면 일부 요청이 매우 느리다는 신호입니다.

---

# 도전 과제 ④ — Rate Limit (`-rps` 옵션)

복습 과제 ②의 RateLimiter를 통합합니다.

## `main.go`에 옵션 추가

```go
var rps = flag.Int("rps", 0, "초당 요청 제한 (0=무제한)")
```

## Pool 수정

```go
type Pool struct {
    // ... 기존 필드 ...
    limiter *RateLimiter
}

func NewPoolWithLimit(numWorkers, rps int) *Pool {
    p := &Pool{
        NumWorkers: numWorkers,
        targets:    make(chan Target),
        results:    make(chan Result, numWorkers*2),
    }
    if rps > 0 {
        p.limiter = NewRateLimiter(rps)
    }
    return p
}

func (p *Pool) workerLoop(ctx context.Context, id int) {
    for {
        select {
        case <-ctx.Done():
            return
        case t, ok := <-p.targets:
            if !ok {
                return
            }

            // Rate limit 적용
            if p.limiter != nil {
                if err := p.limiter.Wait(ctx); err != nil {
                    return
                }
            }

            r := CheckWithRetry(ctx, t.URL, DefaultRetry)
            // ... 나머지 처리
        }
    }
}
```

## 실행

```bash
# 100개 URL을 초당 5개로 제한
./bin/healthcheck -w 10 -rps 5 url1 url2 ... url100
```

워커는 10개로 동시 처리하되, **전체 합계가 초당 5회 이내**로 제한됩니다.

---

# 도전 과제 ⑤ — 로그 분석 에러 채널 분리

4일차 8교시 로그 파이프라인의 파싱 실패를 별도 채널로.

## `stage_parse.go` 수정

```go
func parseStage(
    ctx context.Context,
    in <-chan LogLine,
    numWorkers int,
) (<-chan LogEntry, <-chan ParseError) {
    out := make(chan LogEntry, 100)
    errCh := make(chan ParseError, 100)

    var wg sync.WaitGroup
    for i := 0; i < numWorkers; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            for ll := range in {
                entry, err := parseOne(ll)
                if err != nil {
                    select {
                    case errCh <- ParseError{Source: ll.Source, Line: ll.Line, Err: err}:
                    case <-ctx.Done():
                        return
                    }
                    continue
                }
                select {
                case out <- entry:
                case <-ctx.Done():
                    return
                }
            }
        }()
    }

    go func() {
        wg.Wait()
        close(out)
        close(errCh)
    }()

    return out, errCh
}

type ParseError struct {
    Source string
    Line   string
    Err    error
}

func parseOne(ll LogLine) (LogEntry, error) {
    // ... 기존 로직, 에러 분리
}
```

## `main.go`에서 두 채널 처리

```go
lines := readFiles(ctx, paths)
parsed, parseErrors := parseStage(ctx, lines, 4)

// 에러는 별도 고루틴에서 stderr로
go func() {
    for pe := range parseErrors {
        fmt.Fprintf(os.Stderr, "파싱 실패 [%s]: %s (%v)\n",
            pe.Source, pe.Line, pe.Err)
    }
}()

errors := filterErrors(ctx, parsed)
// ... 나머지 파이프라인
```

## 학습 포인트

- **에러를 정상 흐름에서 분리** → 깨끗한 데이터 경로
- 에러 채널은 보통 더 작은 버퍼 (자주 발생 안 함 가정)
- 두 채널 모두 같은 `wg.Wait()` 이후 닫음

---

# 🎯 4일차 솔루션 마무리

| 솔루션 | 핵심 학습 |
|---|---|
| Web Scraper | Worker Pool + ctx + 재시도 |
| Rate Limiter | Token bucket, `chan struct{}` 활용 |
| Context Tree | 부모-자식 전파 시각화 |
| 제네릭 Pipeline | Go 1.18+ 제네릭으로 재사용 |
| 헬스체커 재시도 | 지수 백오프 패턴 |
| JSON 출력 | 외부 도구 친화적 출력 |
| 응답 시간 통계 | P50/P95/P99 계산 |
| Rate Limit 통합 | 워커 풀과 결합 |
| 에러 채널 분리 | 정상/에러 흐름 격리 |

다음은 [5일차 솔루션](./Go언어프로그래밍_5일차_솔루션.md)으로 이어집니다.
