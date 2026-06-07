# Go 1일차 — 도전 과제 및 복습 과제 솔루션

> 1일차 강의 자료의 도전 과제(8교시 wordcount 확장)와 복습 과제(FizzBuzz, Palindrome, Stack) 솔루션입니다.
> 모든 코드는 Go 1.22 이상에서 동작합니다.

---

## 📑 목차

| 구분 | 과제 | 난이도 |
|---|---|---|
| 복습 ① | FizzBuzz | ⭐ |
| 복습 ② | 회문(Palindrome) 검사 | ⭐⭐ |
| 복습 ③ | 슬라이스 기반 스택 | ⭐⭐ |
| 도전 ① | 단어 카운트 — 대소문자 통일 | ⭐ |
| 도전 ② | 단어 카운트 — 구두점 제거 | ⭐⭐ |
| 도전 ③ | 단어 카운트 — `-n` 옵션 (`flag` 패키지) | ⭐⭐ |
| 도전 ④ | 단어 카운트 — 최소 길이 필터 | ⭐ |

---

# 복습 과제 ① — FizzBuzz

## 문제

1부터 30까지 출력하되, 3의 배수는 `Fizz`, 5의 배수는 `Buzz`, 둘 다이면 `FizzBuzz`로 대체.

## 풀이 핵심

- **순서 중요**: 15는 3과 5의 공배수이므로 **FizzBuzz 검사가 먼저**.
- Go의 `for`는 C와 동일하게 사용 가능.

## 솔루션 — `fizzbuzz.go`

```go
package main

import "fmt"

func main() {
    for i := 1; i <= 30; i++ {
        switch {
        case i%15 == 0:
            fmt.Println("FizzBuzz")
        case i%3 == 0:
            fmt.Println("Fizz")
        case i%5 == 0:
            fmt.Println("Buzz")
        default:
            fmt.Println(i)
        }
    }
}
```

## 변형 1 — 함수로 분리 (테스트 용이성)

```go
package main

import (
    "fmt"
    "strconv"
)

func fizzbuzz(n int) string {
    switch {
    case n%15 == 0:
        return "FizzBuzz"
    case n%3 == 0:
        return "Fizz"
    case n%5 == 0:
        return "Buzz"
    default:
        return strconv.Itoa(n)
    }
}

func main() {
    for i := 1; i <= 30; i++ {
        fmt.Println(fizzbuzz(i))
    }
}
```

## 변형 2 — `switch` 없이 문자열 결합

```go
func fizzbuzz(n int) string {
    s := ""
    if n%3 == 0 { s += "Fizz" }
    if n%5 == 0 { s += "Buzz" }
    if s == ""  { s = strconv.Itoa(n) }
    return s
}
```

3과 5만 있을 때는 단순하지만, 7이나 11이 추가되면 이 방식이 더 깔끔합니다.

## 실행

```bash
go run fizzbuzz.go
# 1, 2, Fizz, 4, Buzz, Fizz, 7, 8, Fizz, Buzz, 11, Fizz, 13, 14, FizzBuzz, ...
```

---

# 복습 과제 ② — 회문(Palindrome) 검사

## 문제

문자열이 회문인지 판별하는 `isPalindrome(s string) bool` 작성. 한글, 대소문자, 공백, 구두점을 어떻게 처리할지 결정.

## 풀이 핵심

- C의 `char*` 인덱싱은 바이트 단위라 한글이 깨짐.
- **Go에서는 `[]rune`으로 변환**해서 유니코드 코드포인트 단위로 비교.
- 대소문자 무시는 `unicode.ToLower`.

## 솔루션 — `palindrome.go`

```go
package main

import (
    "fmt"
    "unicode"
)

func isPalindrome(s string) bool {
    runes := []rune(s)
    i, j := 0, len(runes)-1
    for i < j {
        // 공백/구두점 건너뛰기
        for i < j && !isAlphaNum(runes[i]) {
            i++
        }
        for i < j && !isAlphaNum(runes[j]) {
            j--
        }
        if unicode.ToLower(runes[i]) != unicode.ToLower(runes[j]) {
            return false
        }
        i++
        j--
    }
    return true
}

func isAlphaNum(r rune) bool {
    return unicode.IsLetter(r) || unicode.IsDigit(r)
}

func main() {
    cases := []string{
        "racecar",
        "hello",
        "A man a plan a canal Panama",
        "기러기",
        "토마토",
        "안녕하세요",
        "Was it a car or a cat I saw?",
        "",
    }
    for _, c := range cases {
        fmt.Printf("%-40q → %v\n", c, isPalindrome(c))
    }
}
```

## 실행 결과

```
"racecar"                                → true
"hello"                                  → false
"A man a plan a canal Panama"            → true
"기러기"                                  → true
"토마토"                                  → true
"안녕하세요"                              → false
"Was it a car or a cat I saw?"           → true
""                                       → true
```

## 핵심 포인트

| 함정 | 해결책 |
|---|---|
| `s[i]`는 **바이트** | `[]rune(s)`로 변환 |
| `len(s)`도 **바이트 수** | `len(runes)` 사용 |
| 대소문자 비교 | `unicode.ToLower` |
| 영문/한글 모두 지원 | `unicode.IsLetter` |

## 단위 테스트 (보너스)

`palindrome_test.go`:

```go
package main

import "testing"

func TestIsPalindrome(t *testing.T) {
    tests := []struct {
        input string
        want  bool
    }{
        {"racecar", true},
        {"hello", false},
        {"A man a plan a canal Panama", true},
        {"기러기", true},
        {"", true},
    }
    for _, tc := range tests {
        t.Run(tc.input, func(t *testing.T) {
            got := isPalindrome(tc.input)
            if got != tc.want {
                t.Errorf("isPalindrome(%q) = %v; want %v",
                    tc.input, got, tc.want)
            }
        })
    }
}
```

```bash
go test -v
```

---

# 복습 과제 ③ — 슬라이스 기반 스택

## 문제

`Push`, `Pop`, `Peek` 메서드를 갖는 스택 자료구조 구현.

## 풀이 핵심

- Go 슬라이스는 동적 배열이라 스택의 backing store로 완벽.
- `append`로 Push, `s[:len-1]`로 Pop.
- 빈 스택 처리는 **`error` 또는 `bool` 반환**.

## 솔루션 — `stack.go` (제네릭, Go 1.18+)

```go
package main

import (
    "errors"
    "fmt"
)

type Stack[T any] struct {
    items []T
}

func NewStack[T any]() *Stack[T] {
    return &Stack[T]{items: make([]T, 0, 8)}
}

func (s *Stack[T]) Push(v T) {
    s.items = append(s.items, v)
}

// Pop은 빈 스택일 때 에러 반환
func (s *Stack[T]) Pop() (T, error) {
    var zero T
    if len(s.items) == 0 {
        return zero, errors.New("스택이 비어있음")
    }
    top := s.items[len(s.items)-1]
    s.items = s.items[:len(s.items)-1]
    return top, nil
}

// Peek은 (값, ok) 패턴
func (s *Stack[T]) Peek() (T, bool) {
    var zero T
    if len(s.items) == 0 {
        return zero, false
    }
    return s.items[len(s.items)-1], true
}

func (s *Stack[T]) Len() int     { return len(s.items) }
func (s *Stack[T]) IsEmpty() bool { return len(s.items) == 0 }

func main() {
    // int 스택
    s := NewStack[int]()
    s.Push(10)
    s.Push(20)
    s.Push(30)

    if top, ok := s.Peek(); ok {
        fmt.Println("Peek:", top) // 30
    }

    for !s.IsEmpty() {
        v, _ := s.Pop()
        fmt.Println("Pop:", v)
    }
    // 30, 20, 10

    // string 스택도 같은 코드로
    ss := NewStack[string]()
    ss.Push("a")
    ss.Push("b")
    v, _ := ss.Pop()
    fmt.Println(v) // b
}
```

## 변형 — 제네릭 없이 (Go 1.17 이하)

`interface{}` (`any`)를 쓰면 됩니다.

```go
type Stack struct {
    items []any
}

func (s *Stack) Push(v any)        { s.items = append(s.items, v) }
func (s *Stack) Pop() (any, error) { /* 위와 동일 */ }
```

다만 꺼낼 때마다 **타입 단언**(`v.(int)`)이 필요해서 제네릭이 훨씬 깔끔합니다.

## 활용 예 — 괄호 매칭

스택의 고전적 응용입니다.

```go
func isBalanced(s string) bool {
    stack := NewStack[rune]()
    pairs := map[rune]rune{')': '(', ']': '[', '}': '{'}

    for _, r := range s {
        switch r {
        case '(', '[', '{':
            stack.Push(r)
        case ')', ']', '}':
            top, err := stack.Pop()
            if err != nil || top != pairs[r] {
                return false
            }
        }
    }
    return stack.IsEmpty()
}

func main() {
    fmt.Println(isBalanced("(a+b)*[c-{d/e}]")) // true
    fmt.Println(isBalanced("(()"))              // false
}
```

---

# 도전 과제 — 단어 카운트(`wordcount`) 확장

1일차 8교시 단어 빈도수 계산기 확장. 4가지 기능을 한꺼번에 추가합니다.

## 요구사항 종합

1. **대소문자 통일** — "Go"와 "go" 동일 취급
2. **구두점 제거** — "hello," → "hello"
3. **상위 N개 인자** — `-n 5` 옵션 (`flag` 패키지)
4. **최소 길이 필터** — `-min 3` 옵션

## 최종 솔루션 — `wordcount.go`

```go
package main

import (
    "bufio"
    "flag"
    "fmt"
    "io"
    "os"
    "sort"
    "strings"
    "unicode"
)

type wordFreq struct {
    Word  string
    Count int
}

// 단어 정규화: 소문자화 + 좌우 구두점 제거
func normalize(word string) string {
    w := strings.ToLower(word)
    return strings.TrimFunc(w, func(r rune) bool {
        return !unicode.IsLetter(r) && !unicode.IsDigit(r)
    })
}

func countWords(r io.Reader, minLen int) map[string]int {
    counts := make(map[string]int)
    scanner := bufio.NewScanner(r)
    scanner.Split(bufio.ScanWords)
    for scanner.Scan() {
        w := normalize(scanner.Text())
        if len([]rune(w)) < minLen || w == "" {
            continue
        }
        counts[w]++
    }
    return counts
}

func topN(counts map[string]int, n int) []wordFreq {
    list := make([]wordFreq, 0, len(counts))
    for w, c := range counts {
        list = append(list, wordFreq{w, c})
    }
    sort.Slice(list, func(i, j int) bool {
        if list[i].Count != list[j].Count {
            return list[i].Count > list[j].Count
        }
        return list[i].Word < list[j].Word // 동률은 사전순
    })
    if len(list) > n {
        list = list[:n]
    }
    return list
}

func openInput(args []string) (io.ReadCloser, error) {
    if len(args) > 0 {
        return os.Open(args[0])
    }
    return io.NopCloser(os.Stdin), nil
}

func main() {
    var (
        topCount = flag.Int("n", 10, "출력할 상위 단어 개수")
        minLen   = flag.Int("min", 1, "단어의 최소 길이")
    )
    flag.Usage = func() {
        fmt.Fprintf(flag.CommandLine.Output(),
            "사용법: %s [옵션] [파일경로]\n옵션:\n", os.Args[0])
        flag.PrintDefaults()
    }
    flag.Parse()

    in, err := openInput(flag.Args())
    if err != nil {
        fmt.Fprintln(os.Stderr, "입력 열기 실패:", err)
        os.Exit(1)
    }
    defer in.Close()

    counts := countWords(in, *minLen)
    top := topN(counts, *topCount)

    fmt.Printf("=== Top %d (min=%d) ===\n", *topCount, *minLen)
    for i, wf := range top {
        fmt.Printf("%2d. %-20s %d\n", i+1, wf.Word, wf.Count)
    }
}
```

## 실행 결과

테스트 입력:

```bash
cat > sample.txt << 'EOF'
Go is a programming language. Go was created at Google.
go is fast! Go is simple. go is fun. Go, go, GO!
The QUICK brown fox jumps over the LAZY dog.
A B C 1 2 3
EOF
```

### 기본 실행

```bash
go run wordcount.go sample.txt
```

```
=== Top 10 (min=1) ===
 1. go                   8
 2. is                   4
 3. a                    2
 4. the                  2
 5. at                   1
 ...
```

### 옵션 활용

```bash
# 상위 5개 + 최소 3글자
go run wordcount.go -n 5 -min 3 sample.txt
```

`go`(2글자)와 `is`(2글자)가 필터링되어 결과가 달라집니다.

### stdin 모드

```bash
echo "go go GO! Python python C++ C++ C++ C++" | go run wordcount.go -min 1
```

```
=== Top 10 (min=1) ===
 1. c                    4
 2. go                   3
 3. python               2
```

(`++`가 제거되어 `c`만 남음)

## 핵심 학습 포인트

| 기능 | 사용 표준 라이브러리 |
|---|---|
| 옵션 파싱 | `flag` |
| 단어 분할 | `bufio.Scanner` + `ScanWords` |
| 소문자화 | `strings.ToLower` |
| 구두점 제거 | `strings.TrimFunc` + `unicode.IsLetter` |
| 정렬 | `sort.Slice` (안정 정렬은 `sort.SliceStable`) |

## 추가 확장 아이디어

5일차에서 배울 내용을 미리 적용해보면:

- **테스트 작성** — `normalize`, `countWords`, `topN`을 표 기반 테스트로 검증
- **JSON 출력** — `-format json` 옵션
- **파일 여러 개 받기** — `flag.Args()`를 순회
- **워드 클라우드용 CSV 출력** — `encoding/csv`

---

# 🎯 1일차 솔루션 마무리

5가지 과제를 통해 다음을 종합 점검했습니다.

| 학습 요소 | 어디서 등장? |
|---|---|
| `for` 루프 + `switch` | FizzBuzz |
| `[]rune` 변환과 유니코드 | Palindrome |
| 슬라이스 동적 확장 | Stack |
| 메서드와 리시버 | Stack |
| 제네릭 (1.18+) | Stack |
| `map`과 zero value | wordcount |
| `flag` 패키지 | wordcount |
| 정렬 (`sort.Slice`) | wordcount, topN |
| 표준 라이브러리 | wordcount 전반 |

다음은 [2일차 솔루션](./Go언어프로그래밍_2일차_솔루션.md)으로 이어집니다.
