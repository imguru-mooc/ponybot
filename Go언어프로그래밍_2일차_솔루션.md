# Go 2일차 — 도전 과제 및 복습 과제 솔루션

> 2일차 강의 자료의 도전 과제(8교시 calc 확장)와 복습 과제(textutil 프로젝트, 사용자 정의 에러 타입, go mod 명령) 솔루션입니다.

---

## 📑 목차

| 구분 | 과제 | 난이도 |
|---|---|---|
| 복습 ① | `textutil` — 멀티 패키지 wc 흉내 도구 | ⭐⭐⭐ |
| 복습 ② | 사용자 정의 에러 타입 3가지 + `errors.As` | ⭐⭐ |
| 복습 ③ | `go mod why`, `go mod graph` 활용 | ⭐ |
| 도전 ① | `calc` + `mod` (나머지) 연산 | ⭐ |
| 도전 ② | 계산 이력 저장 (`CALC_HISTORY` 환경 변수) | ⭐⭐ |
| 도전 ③ | `cobra`로 CLI 풍부하게 | ⭐⭐⭐ |
| 도전 ④ | 벤치마크 테스트 추가 | ⭐⭐ |

---

# 복습 과제 ① — `textutil` 멀티 패키지 프로젝트

## 문제

`wc` (word count) 흉내 도구를 멀티 패키지로 구성. 줄 / 단어 / 문자 개수 출력. 에러 처리는 `errors.Is`로 분기.

## 프로젝트 구조

```
textutil/
├── go.mod
├── Makefile
├── cmd/textutil/main.go
├── internal/processor/
│   ├── processor.go
│   └── processor_test.go
└── pkg/fileio/
    └── fileio.go
```

## 셋업

```bash
mkdir -p ~/go-class/day2-solutions/textutil
cd ~/go-class/day2-solutions/textutil
go mod init textutil

mkdir -p cmd/textutil
mkdir -p internal/processor
mkdir -p pkg/fileio
```

## Step 1 — `pkg/fileio/fileio.go`

외부에서 import 가능한 파일 I/O 헬퍼.

```go
package fileio

import (
    "errors"
    "fmt"
    "io"
    "os"
)

// 미리 정의된 에러 (sentinel) - errors.Is로 비교 가능
var (
    ErrNotFound     = errors.New("파일을 찾을 수 없음")
    ErrNoPermission = errors.New("파일 접근 권한 없음")
)

// Open은 OS 에러를 sentinel로 변환해 반환
func Open(path string) (io.ReadCloser, error) {
    f, err := os.Open(path)
    if err != nil {
        switch {
        case errors.Is(err, os.ErrNotExist):
            return nil, fmt.Errorf("%w: %s", ErrNotFound, path)
        case errors.Is(err, os.ErrPermission):
            return nil, fmt.Errorf("%w: %s", ErrNoPermission, path)
        default:
            return nil, err
        }
    }
    return f, nil
}
```

`%w`로 sentinel을 래핑하여 컨텍스트(파일 경로)도 함께 전달합니다.

## Step 2 — `internal/processor/processor.go`

핵심 카운팅 로직.

```go
package processor

import (
    "bufio"
    "io"
    "unicode/utf8"
)

type Stats struct {
    Lines int
    Words int
    Chars int  // 문자 수 (rune 단위)
    Bytes int  // 바이트 수
}

func Count(r io.Reader) (Stats, error) {
    var s Stats
    scanner := bufio.NewScanner(r)
    // 매우 긴 줄 지원
    buf := make([]byte, 0, 64*1024)
    scanner.Buffer(buf, 1024*1024)

    for scanner.Scan() {
        s.Lines++
        line := scanner.Bytes()
        s.Bytes += len(line) + 1 // 개행 포함
        s.Chars += utf8.RuneCount(line) + 1
        s.Words += countWords(line)
    }
    if err := scanner.Err(); err != nil {
        return s, err
    }
    return s, nil
}

func countWords(b []byte) int {
    count := 0
    inWord := false
    for i := 0; i < len(b); {
        r, size := utf8.DecodeRune(b[i:])
        if r == ' ' || r == '\t' {
            inWord = false
        } else if !inWord {
            count++
            inWord = true
        }
        i += size
    }
    return count
}
```

## Step 3 — `internal/processor/processor_test.go`

```go
package processor

import (
    "strings"
    "testing"
)

func TestCount(t *testing.T) {
    tests := []struct {
        name  string
        input string
        want  Stats
    }{
        {"빈 입력", "", Stats{0, 0, 0, 0}},
        {"한 줄", "hello world\n",
            Stats{Lines: 1, Words: 2, Chars: 12, Bytes: 12}},
        {"여러 줄", "go\nis\nfun\n",
            Stats{Lines: 3, Words: 3, Chars: 9, Bytes: 9}},
        {"한글 포함", "안녕 hello\n",
            Stats{Lines: 1, Words: 2, Chars: 9, Bytes: 13}},
    }
    for _, tc := range tests {
        t.Run(tc.name, func(t *testing.T) {
            got, err := Count(strings.NewReader(tc.input))
            if err != nil {
                t.Fatal(err)
            }
            if got.Lines != tc.want.Lines {
                t.Errorf("Lines = %d, want %d", got.Lines, tc.want.Lines)
            }
            if got.Words != tc.want.Words {
                t.Errorf("Words = %d, want %d", got.Words, tc.want.Words)
            }
        })
    }
}
```

## Step 4 — `cmd/textutil/main.go`

CLI 진입점. `flag` 패키지 + 에러 분기.

```go
package main

import (
    "errors"
    "fmt"
    "flag"
    "io"
    "os"

    "textutil/internal/processor"
    "textutil/pkg/fileio"
)

func main() {
    var (
        showLines = flag.Bool("l", false, "줄 수만 출력")
        showWords = flag.Bool("w", false, "단어 수만 출력")
        showChars = flag.Bool("c", false, "문자 수만 출력")
    )
    flag.Parse()

    paths := flag.Args()
    if len(paths) == 0 {
        paths = []string{"-"}
    }

    var total processor.Stats
    var hasError bool

    for _, p := range paths {
        var (
            r   io.Reader
            err error
        )
        if p == "-" {
            r = os.Stdin
        } else {
            f, e := fileio.Open(p)
            if e != nil {
                hasError = true
                handleError(e, p)
                continue
            }
            defer f.Close()
            r = f
        }

        stats, err := processor.Count(r)
        if err != nil {
            hasError = true
            fmt.Fprintf(os.Stderr, "처리 실패 (%s): %v\n", p, err)
            continue
        }

        printStats(stats, p, *showLines, *showWords, *showChars)
        total.Lines += stats.Lines
        total.Words += stats.Words
        total.Chars += stats.Chars
    }

    if len(paths) > 1 {
        fmt.Println("---")
        printStats(total, "total", *showLines, *showWords, *showChars)
    }

    if hasError {
        os.Exit(1)
    }
}

func handleError(err error, path string) {
    switch {
    case errors.Is(err, fileio.ErrNotFound):
        fmt.Fprintf(os.Stderr, "에러: 파일 없음 — %s\n", path)
    case errors.Is(err, fileio.ErrNoPermission):
        fmt.Fprintf(os.Stderr, "에러: 권한 부족 — %s\n", path)
    default:
        fmt.Fprintf(os.Stderr, "알 수 없는 에러 (%s): %v\n", path, err)
    }
}

func printStats(s processor.Stats, label string, showL, showW, showC bool) {
    // 옵션이 하나도 없으면 모두 출력
    if !showL && !showW && !showC {
        showL, showW, showC = true, true, true
    }
    parts := []string{}
    if showL {
        parts = append(parts, fmt.Sprintf("%6d", s.Lines))
    }
    if showW {
        parts = append(parts, fmt.Sprintf("%6d", s.Words))
    }
    if showC {
        parts = append(parts, fmt.Sprintf("%6d", s.Chars))
    }
    line := ""
    for _, p := range parts {
        line += p + " "
    }
    fmt.Printf("%s %s\n", line, label)
}
```

## Step 5 — Makefile

```makefile
BINARY := textutil

.PHONY: all build test fmt vet clean run

all: fmt vet test build

build:
	go build -o bin/$(BINARY) ./cmd/$(BINARY)

test:
	go test -race ./...

fmt:
	go fmt ./...

vet:
	go vet ./...

run: build
	./bin/$(BINARY) cmd/textutil/main.go

clean:
	rm -rf bin/
```

## 실행 결과

```bash
make build
./bin/textutil cmd/textutil/main.go internal/processor/processor.go

# 출력 예시:
#     85     220   2150  cmd/textutil/main.go
#     38     100   1200  internal/processor/processor.go
# ---
#    123     320   3350  total
```

### 에러 분기 테스트

```bash
./bin/textutil 없는파일.txt
# 에러: 파일 없음 — 없는파일.txt

./bin/textutil /etc/shadow
# 에러: 권한 부족 — /etc/shadow
```

`errors.Is`로 분기된 친절한 에러 메시지가 나옵니다.

---

# 복습 과제 ② — 사용자 정의 에러 타입 3가지 + `errors.As`

## 문제

3가지 이상의 사용자 정의 에러 타입을 정의하고, `errors.As`로 각각 추출하는 예제 작성.

## 솔루션 — `errors_demo.go`

```go
package main

import (
    "errors"
    "fmt"
    "time"
)

// === 에러 타입 1: 검증 에러 ===
type ValidationError struct {
    Field   string
    Value   any
    Message string
}

func (e *ValidationError) Error() string {
    return fmt.Sprintf("필드 %q 검증 실패 (값=%v): %s",
        e.Field, e.Value, e.Message)
}

// === 에러 타입 2: 네트워크 에러 ===
type NetworkError struct {
    URL        string
    StatusCode int
    Timeout    time.Duration
    Retryable  bool
}

func (e *NetworkError) Error() string {
    return fmt.Sprintf("네트워크 에러: %s [status=%d, retryable=%v]",
        e.URL, e.StatusCode, e.Retryable)
}

// === 에러 타입 3: 데이터베이스 에러 ===
type DBError struct {
    Query    string
    Table    string
    RowsHit  int
    Original error // 원본 에러 래핑
}

func (e *DBError) Error() string {
    return fmt.Sprintf("DB 에러 (table=%s, rows=%d): %v",
        e.Table, e.RowsHit, e.Original)
}

// Unwrap을 구현하면 errors.Is/As가 체인을 따라감
func (e *DBError) Unwrap() error {
    return e.Original
}

// === 비즈니스 로직 ===

func validateAge(age int) error {
    if age < 0 || age > 150 {
        return &ValidationError{
            Field:   "age",
            Value:   age,
            Message: "0~150 범위여야 함",
        }
    }
    return nil
}

func fetchUser(id int) error {
    // 시뮬레이션: ID 1은 정상, 2는 네트워크 에러, 3은 DB 에러
    switch id {
    case 1:
        return nil
    case 2:
        return &NetworkError{
            URL:        "https://api.example.com/users/2",
            StatusCode: 503,
            Timeout:    5 * time.Second,
            Retryable:  true,
        }
    case 3:
        return &DBError{
            Query:    "SELECT * FROM users WHERE id=3",
            Table:    "users",
            RowsHit:  0,
            Original: errors.New("connection refused"),
        }
    default:
        return errors.New("unknown error")
    }
}

// === 에러를 분류해서 처리 ===
func handleError(err error) {
    if err == nil {
        fmt.Println("정상")
        return
    }

    var validErr *ValidationError
    var netErr *NetworkError
    var dbErr *DBError

    switch {
    case errors.As(err, &validErr):
        fmt.Printf("[검증 실패] 필드=%s, 메시지=%s\n",
            validErr.Field, validErr.Message)

    case errors.As(err, &netErr):
        if netErr.Retryable {
            fmt.Printf("[네트워크] 재시도 가능: %s\n", netErr.URL)
        } else {
            fmt.Printf("[네트워크] 영구 실패: %s\n", netErr.URL)
        }

    case errors.As(err, &dbErr):
        fmt.Printf("[DB] 테이블=%s, 원인=%v\n", dbErr.Table, dbErr.Original)

    default:
        fmt.Printf("[기타] %v\n", err)
    }
}

func main() {
    // 1. 검증 에러
    handleError(validateAge(-5))

    // 2. 네트워크 에러
    handleError(fetchUser(2))

    // 3. DB 에러
    handleError(fetchUser(3))

    // 4. 알 수 없는 에러
    handleError(fetchUser(999))

    // 5. 정상
    handleError(fetchUser(1))

    // === errors.As가 체인을 따라가는지 확인 ===
    wrapped := fmt.Errorf("작업 실패: %w", fetchUser(3))
    var dbErr *DBError
    if errors.As(wrapped, &dbErr) {
        fmt.Println("\n래핑된 DB 에러 추출 성공:", dbErr.Table)
    }
}
```

## 실행 결과

```
[검증 실패] 필드=age, 메시지=0~150 범위여야 함
[네트워크] 재시도 가능: https://api.example.com/users/2
[DB] 테이블=users, 원인=connection refused
[기타] unknown error
정상

래핑된 DB 에러 추출 성공: users
```

## 핵심 학습 포인트

| 패턴 | 효과 |
|---|---|
| 구조체 + `Error()` 메서드 | 컨텍스트 풍부한 에러 |
| `Unwrap()` 구현 | `errors.Is/As`가 체인을 따라감 |
| `errors.As(err, &target)` | 타입 추출 → 필드 접근 |
| `switch` + `errors.As` | 타입별 분기 처리 |

---

# 복습 과제 ③ — `go mod why`, `go mod graph` 활용

## 문제

좋아하는 프로젝트에서 의존성 트리를 분석하는 명령어 실습.

## 실습 시나리오

작은 프로젝트를 만들고 외부 라이브러리를 추가해 분석합니다.

```bash
mkdir ~/go-class/day2-solutions/deps
cd ~/go-class/day2-solutions/deps
go mod init depstest
```

`main.go`:

```go
package main

import (
    "fmt"
    "github.com/sirupsen/logrus"
    "github.com/google/uuid"
)

func main() {
    log := logrus.New()
    log.Info("UUID:", uuid.New())
    fmt.Println("done")
}
```

```bash
go mod tidy
```

## ① `go mod graph` — 전체 의존성 그래프

```bash
go mod graph
```

출력 (일부):
```
depstest github.com/sirupsen/logrus@v1.9.3
depstest github.com/google/uuid@v1.6.0
github.com/sirupsen/logrus@v1.9.3 golang.org/x/sys@v0.0.0-...
github.com/sirupsen/logrus@v1.9.3 github.com/stretchr/testify@v1.7.0
```

각 줄은 "**A가 B에 의존한다**"는 의미입니다.

### 시각화 — Graphviz로

```bash
go mod graph | awk '{print "\"" $1 "\" -> \"" $2 "\";"}' \
  | { echo "digraph G {"; cat; echo "}"; } > deps.dot
dot -Tpng deps.dot -o deps.png
xdg-open deps.png
```

브라우저에서 의존성 그래프를 한눈에 볼 수 있습니다.

## ② `go mod why` — 특정 패키지가 왜 들어왔는가?

```bash
go mod why golang.org/x/sys
```

```
# golang.org/x/sys
github.com/sirupsen/logrus
golang.org/x/sys/unix
```

→ `logrus`가 `golang.org/x/sys`를 끌어왔음을 알 수 있습니다.

```bash
go mod why github.com/stretchr/testify
```

`testify`는 우리 코드와 직접 연관이 없지만 의존성으로 들어왔습니다. 보통 테스트 의존성으로 같이 따라옵니다.

## ③ `go list` — 더 상세한 정보

```bash
# 사용 중인 모든 모듈
go list -m all

# 업데이트 가능한 모듈
go list -m -u all

# JSON 형태 (스크립트 처리용)
go list -m -json all | jq '.Path'
```

## ④ 의존성 정리 명령들

```bash
# 사용 안 하는 의존성 제거
go mod tidy

# vendor 디렉터리 생성 (오프라인 빌드용)
go mod vendor

# go.sum 검증
go mod verify

# 모듈 캐시 정리
go clean -modcache  # 주의: 모든 캐시 삭제
```

## 실전 활용 예 — 취약점 점검

```bash
# govulncheck 설치 (한 번만)
go install golang.org/x/vuln/cmd/govulncheck@latest

# 프로젝트 취약점 점검
govulncheck ./...
```

CVE가 알려진 의존성이 있으면 경고. CI 파이프라인에 포함하면 좋습니다.

---

# 도전 과제 ① — `calc` + `mod` 연산 추가

2일차 8교시 calc에 나머지 연산 추가.

## 수정 위치 — `internal/calculator/calculator.go`

```go
func Calculate(op string, a, b float64) (float64, error) {
    switch op {
    case "add":
        return a + b, nil
    case "sub":
        return a - b, nil
    case "mul":
        return a * b, nil
    case "div":
        if b == 0 {
            return 0, fmt.Errorf("a=%v, b=%v: %w", a, b, ErrDivByZero)
        }
        return a / b, nil
    case "mod":  // ← 추가
        if b == 0 {
            return 0, fmt.Errorf("a=%v, b=%v: %w", a, b, ErrDivByZero)
        }
        return math.Mod(a, b), nil
    default:
        return 0, fmt.Errorf("지원하지 않는 연산: %q (지원: add, sub, mul, div, mod)", op)
    }
}
```

import에 `"math"` 추가.

## `cmd/calc/main.go`의 `symbol()`도 업데이트

```go
func symbol(op string) string {
    switch op {
    case "add": return "+"
    case "sub": return "-"
    case "mul": return "×"
    case "div": return "÷"
    case "mod": return "mod"  // ← 추가
    }
    return op
}
```

## 테스트 추가

```go
{"mod", "mod", 10, 3, 1},      // 10 % 3 = 1
{"mod 음수", "mod", -7, 3, -1}, // -7 % 3 = -1 (Go의 부호 규칙)
```

`math.Mod`는 IEEE 754 표준 규칙을 따릅니다 (피제수 부호 따라감).

## 실행

```bash
./bin/calc mod 10 3
# 10 mod 3 = 1

./bin/calc mod 17 5
# 17 mod 5 = 2
```

---

# 도전 과제 ② — 계산 이력 저장

`CALC_HISTORY=on` 환경 변수 시 결과를 `~/.calc-history`에 기록.

## `cmd/calc/main.go` 수정

```go
package main

import (
    // 기존 import...
    "os"
    "path/filepath"
    "time"
)

func appendHistory(line string) error {
    if os.Getenv("CALC_HISTORY") != "on" {
        return nil
    }

    home, err := os.UserHomeDir()
    if err != nil {
        return err
    }
    path := filepath.Join(home, ".calc-history")

    f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
    if err != nil {
        return err
    }
    defer f.Close()

    ts := time.Now().Format("2006-01-02 15:04:05")
    _, err = fmt.Fprintf(f, "%s | %s\n", ts, line)
    return err
}

func main() {
    // ... 기존 코드 ...

    result, err := calculator.Calculate(args.Op, args.A, args.B)
    // 에러 처리...

    line := fmt.Sprintf("%g %s %g = %g", args.A, symbol(args.Op), args.B, result)
    fmt.Println(line)

    // 이력 기록
    if err := appendHistory(line); err != nil {
        fmt.Fprintln(os.Stderr, "이력 저장 실패:", err)
    }
}
```

## 실행

```bash
# 이력 없이
./bin/calc add 3 5
# 3 + 5 = 8

# 이력 켜기
CALC_HISTORY=on ./bin/calc add 3 5
./bin/calc mul 4 7

cat ~/.calc-history
# 2024-01-15 14:23:01 | 3 + 5 = 8
# 2024-01-15 14:23:02 | 4 × 7 = 28
```

## 학습 포인트

| 기능 | API |
|---|---|
| 환경 변수 읽기 | `os.Getenv` |
| 홈 디렉터리 | `os.UserHomeDir()` |
| 경로 조합 | `filepath.Join` |
| 파일 추가 모드 | `os.O_APPEND \| os.O_CREATE \| os.O_WRONLY` |
| 시간 포맷 | `time.Format("2006-01-02 15:04:05")` |

> Go의 시간 포맷은 **참조 시각 `Mon Jan 2 15:04:05 MST 2006`**을 기준으로 합니다. C의 `strftime`과 다른 점입니다.

---

# 도전 과제 ③ — `cobra`로 CLI 풍부하게

표준 `flag` 패키지 대신 [Cobra](https://github.com/spf13/cobra)를 적용.

## 의존성 추가

```bash
go get github.com/spf13/cobra@latest
```

## `cmd/calc/main.go` 재작성

```go
package main

import (
    "fmt"
    "os"
    "strconv"

    "github.com/spf13/cobra"
    "github.com/myname/calc/internal/calculator"
)

var (
    Version    = "dev"
    verbose    bool
)

var rootCmd = &cobra.Command{
    Use:   "calc",
    Short: "간단한 계산기",
    Long:  "사칙연산과 나머지 연산을 지원하는 CLI 계산기입니다.",
    Version: Version,
}

func init() {
    rootCmd.PersistentFlags().BoolVarP(&verbose, "verbose", "v", false, "상세 출력")

    rootCmd.AddCommand(makeOpCmd("add", "더하기", "+"))
    rootCmd.AddCommand(makeOpCmd("sub", "빼기", "-"))
    rootCmd.AddCommand(makeOpCmd("mul", "곱하기", "×"))
    rootCmd.AddCommand(makeOpCmd("div", "나누기", "÷"))
    rootCmd.AddCommand(makeOpCmd("mod", "나머지", "mod"))
}

func makeOpCmd(op, desc, sym string) *cobra.Command {
    return &cobra.Command{
        Use:   fmt.Sprintf("%s [a] [b]", op),
        Short: desc,
        Args:  cobra.ExactArgs(2),
        RunE: func(cmd *cobra.Command, args []string) error {
            a, err := strconv.ParseFloat(args[0], 64)
            if err != nil {
                return fmt.Errorf("a 파싱 실패: %w", err)
            }
            b, err := strconv.ParseFloat(args[1], 64)
            if err != nil {
                return fmt.Errorf("b 파싱 실패: %w", err)
            }

            if verbose {
                fmt.Printf("[%s] %v %s %v 계산 중...\n", op, a, sym, b)
            }

            result, err := calculator.Calculate(op, a, b)
            if err != nil {
                return err
            }

            fmt.Printf("%g %s %g = %g\n", a, sym, b, result)
            return nil
        },
    }
}

func main() {
    if err := rootCmd.Execute(); err != nil {
        os.Exit(1)
    }
}
```

## Cobra의 장점

```bash
./bin/calc --help
# 자동 생성된 도움말

./bin/calc add --help
# 서브커맨드별 도움말

./bin/calc add 3 5
# 3 + 5 = 8

./bin/calc -v mul 6 7
# [mul] 6 × 7 계산 중...
# 6 × 7 = 42

./bin/calc --version
# calc version dev
```

Cobra는 **kubectl, helm, hugo** 등 대형 CLI 도구가 모두 쓰는 사실상의 표준입니다. 서브커맨드, 자동 도움말, 셸 자동완성까지 지원합니다.

---

# 도전 과제 ④ — 벤치마크 테스트 추가

## `internal/calculator/calculator_test.go`에 추가

```go
package calculator

import "testing"

func BenchmarkCalculate(b *testing.B) {
    benchmarks := []struct {
        name string
        op   string
        a, b float64
    }{
        {"add", "add", 1.5, 2.5},
        {"mul", "mul", 12.34, 56.78},
        {"div", "div", 100.0, 3.0},
        {"mod", "mod", 100.0, 7.0},
    }

    for _, bm := range benchmarks {
        b.Run(bm.name, func(b *testing.B) {
            b.ResetTimer()
            for i := 0; i < b.N; i++ {
                _, _ = Calculate(bm.op, bm.a, bm.b)
            }
        })
    }
}

// 단순 함수 직접 호출과 비교
func BenchmarkDirectAdd(b *testing.B) {
    for i := 0; i < b.N; i++ {
        _ = 1.5 + 2.5
    }
}
```

## Makefile에 타깃 추가

```makefile
.PHONY: bench
bench:
	go test -bench=. -benchmem ./internal/calculator
```

## 실행

```bash
make bench
```

출력 예시:
```
goos: linux
goarch: amd64
BenchmarkCalculate/add-8     200000000   5.2 ns/op   0 B/op   0 allocs/op
BenchmarkCalculate/mul-8     200000000   5.1 ns/op   0 B/op   0 allocs/op
BenchmarkCalculate/div-8     200000000   5.3 ns/op   0 B/op   0 allocs/op
BenchmarkCalculate/mod-8     100000000   8.7 ns/op   0 B/op   0 allocs/op
BenchmarkDirectAdd-8        1000000000   0.3 ns/op   0 B/op   0 allocs/op
```

## 결과 해석

- `Calculate` 호출은 약 5ns
- 직접 덧셈은 0.3ns
- **함수 호출 + switch 분기 오버헤드가 약 5ns**
- mod는 부동소수 모듈로 연산 비용이 더 큼

## 두 버전 성능 비교 — `benchstat`

코드 최적화 전후 비교에 유용합니다.

```bash
go install golang.org/x/perf/cmd/benchstat@latest

# 변경 전
make bench > old.txt

# 코드 수정 후
make bench > new.txt

benchstat old.txt new.txt
# 변화량과 통계적 유의성 표시
```

---

# 🎯 2일차 솔루션 마무리

| 솔루션 | 핵심 학습 |
|---|---|
| `textutil` 프로젝트 | 멀티 패키지 구조, `internal/`, `pkg/`, sentinel 에러 |
| 사용자 정의 에러 3종 | `errors.As`, `Unwrap`, 타입 기반 분기 |
| `go mod why/graph` | 의존성 트리 분석, 시각화 |
| `mod` 연산 추가 | `math.Mod`, 케이스 확장 |
| 이력 저장 | 환경 변수, 파일 I/O, 시간 포맷 |
| Cobra CLI | 서브커맨드, 자동 도움말 |
| 벤치마크 | `b.Run`, `benchstat` 활용 |

다음은 [3일차 솔루션](./Go언어프로그래밍_3일차_솔루션.md)으로 이어집니다.
