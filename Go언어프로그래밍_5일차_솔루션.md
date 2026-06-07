# Go 5일차 — 최종 도전 과제 솔루션

> 5일차 강의 자료의 8.7절 **최종 도전 과제 6개**에 대한 솔루션입니다.
> 7~8교시에서 만든 `userapi` 프로젝트를 확장하는 형태로 제공됩니다.

---

## 📑 목차

| 구분 | 과제 | 난이도 |
|---|---|---|
| 도전 ① | PostgreSQL 연동 (`pgx`) | ⭐⭐⭐ |
| 도전 ② | JWT 인증 미들웨어 | ⭐⭐⭐ |
| 도전 ③ | OpenAPI / Swagger UI | ⭐⭐ |
| 도전 ④ | Prometheus 메트릭 | ⭐⭐⭐ |
| 도전 ⑤ | GitHub Actions CI/CD | ⭐⭐ |
| 도전 ⑥ | 부하 테스트 + pprof 분석 | ⭐⭐⭐⭐ |

---

# 도전 과제 ① — PostgreSQL 연동

## 문제

인메모리 저장소(`MemoryStore`)를 PostgreSQL로 교체. `pgx` 드라이버 사용.

## 솔루션 — 인터페이스 그대로, 구현만 교체

5일차 7교시에서 `Store` **인터페이스**를 정의해 둔 덕분에 구현체만 갈아끼우면 됩니다. 이것이 **인터페이스 기반 설계의 힘**입니다.

### Step 1 — 의존성 추가

```bash
cd ~/go-class/day5/userapi
go get github.com/jackc/pgx/v5
go get github.com/jackc/pgx/v5/pgxpool
```

### Step 2 — DB 스키마

`migrations/001_users.sql`:

```sql
CREATE TABLE IF NOT EXISTS users (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    email      TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
```

### Step 3 — PostgresStore 구현

`internal/user/postgres.go`:

```go
package user

import (
    "context"
    "errors"
    "fmt"
    "time"

    "github.com/jackc/pgx/v5"
    "github.com/jackc/pgx/v5/pgconn"
    "github.com/jackc/pgx/v5/pgxpool"
)

type PostgresStore struct {
    pool *pgxpool.Pool
}

func NewPostgresStore(ctx context.Context, dsn string) (*PostgresStore, error) {
    cfg, err := pgxpool.ParseConfig(dsn)
    if err != nil {
        return nil, fmt.Errorf("DSN 파싱 실패: %w", err)
    }
    cfg.MaxConns = 20
    cfg.MinConns = 2
    cfg.MaxConnLifetime = 30 * time.Minute

    pool, err := pgxpool.NewWithConfig(ctx, cfg)
    if err != nil {
        return nil, fmt.Errorf("연결 풀 생성 실패: %w", err)
    }

    // 연결 확인
    if err := pool.Ping(ctx); err != nil {
        return nil, fmt.Errorf("ping 실패: %w", err)
    }
    return &PostgresStore{pool: pool}, nil
}

func (s *PostgresStore) Close() {
    s.pool.Close()
}

func (s *PostgresStore) Create(ctx context.Context, u *User) error {
    if err := u.Validate(); err != nil {
        return err
    }

    const q = `
        INSERT INTO users (name, email)
        VALUES ($1, $2)
        RETURNING id, created_at, updated_at
    `
    err := s.pool.QueryRow(ctx, q, u.Name, u.Email).
        Scan(&u.ID, &u.CreatedAt, &u.UpdatedAt)

    if err != nil {
        var pgErr *pgconn.PgError
        if errors.As(err, &pgErr) && pgErr.Code == "23505" {
            // unique_violation
            return ErrAlreadyExists
        }
        return fmt.Errorf("INSERT 실패: %w", err)
    }
    return nil
}

func (s *PostgresStore) Get(ctx context.Context, id int) (*User, error) {
    const q = `
        SELECT id, name, email, created_at, updated_at
        FROM users
        WHERE id = $1
    `
    var u User
    err := s.pool.QueryRow(ctx, q, id).
        Scan(&u.ID, &u.Name, &u.Email, &u.CreatedAt, &u.UpdatedAt)

    if err != nil {
        if errors.Is(err, pgx.ErrNoRows) {
            return nil, ErrNotFound
        }
        return nil, fmt.Errorf("SELECT 실패: %w", err)
    }
    return &u, nil
}

func (s *PostgresStore) List(ctx context.Context, offset, limit int) ([]*User, int, error) {
    // 트랜잭션으로 COUNT와 SELECT를 일관성 있게
    tx, err := s.pool.Begin(ctx)
    if err != nil {
        return nil, 0, err
    }
    defer tx.Rollback(ctx)

    var total int
    if err := tx.QueryRow(ctx, `SELECT COUNT(*) FROM users`).Scan(&total); err != nil {
        return nil, 0, err
    }

    const q = `
        SELECT id, name, email, created_at, updated_at
        FROM users
        ORDER BY id
        OFFSET $1 LIMIT $2
    `
    rows, err := tx.Query(ctx, q, offset, limit)
    if err != nil {
        return nil, 0, err
    }
    defer rows.Close()

    var users []*User
    for rows.Next() {
        var u User
        if err := rows.Scan(&u.ID, &u.Name, &u.Email, &u.CreatedAt, &u.UpdatedAt); err != nil {
            return nil, 0, err
        }
        users = append(users, &u)
    }
    if err := rows.Err(); err != nil {
        return nil, 0, err
    }

    if err := tx.Commit(ctx); err != nil {
        return nil, 0, err
    }
    return users, total, nil
}

func (s *PostgresStore) Update(ctx context.Context, u *User) error {
    if err := u.Validate(); err != nil {
        return err
    }
    const q = `
        UPDATE users
        SET name = $1, email = $2, updated_at = NOW()
        WHERE id = $3
        RETURNING updated_at
    `
    err := s.pool.QueryRow(ctx, q, u.Name, u.Email, u.ID).Scan(&u.UpdatedAt)
    if err != nil {
        if errors.Is(err, pgx.ErrNoRows) {
            return ErrNotFound
        }
        return fmt.Errorf("UPDATE 실패: %w", err)
    }
    return nil
}

func (s *PostgresStore) Delete(ctx context.Context, id int) error {
    const q = `DELETE FROM users WHERE id = $1`
    tag, err := s.pool.Exec(ctx, q, id)
    if err != nil {
        return fmt.Errorf("DELETE 실패: %w", err)
    }
    if tag.RowsAffected() == 0 {
        return ErrNotFound
    }
    return nil
}
```

### Step 4 — 인터페이스에 ctx 추가

기존 `Store` 인터페이스를 ctx-aware로 업데이트:

```go
// internal/user/store.go
type Store interface {
    Create(ctx context.Context, u *User) error
    Get(ctx context.Context, id int) (*User, error)
    List(ctx context.Context, offset, limit int) ([]*User, int, error)
    Update(ctx context.Context, u *User) error
    Delete(ctx context.Context, id int) error
}
```

`MemoryStore`도 ctx를 받도록 수정(내부에선 무시해도 OK):

```go
func (s *MemoryStore) Create(_ context.Context, u *User) error {
    // 기존 로직
}
```

### Step 5 — 핸들러에서 ctx 전달

`internal/httpserver/handlers.go`:

```go
func (s *Server) createUser(w http.ResponseWriter, r *http.Request) {
    var u user.User
    if err := json.NewDecoder(r.Body).Decode(&u); err != nil {
        writeError(w, http.StatusBadRequest, "잘못된 JSON")
        return
    }
    if err := s.Store.Create(r.Context(), &u); err != nil {
        // ... 에러 처리
    }
    writeJSON(w, http.StatusCreated, u)
}
```

`r.Context()`는 HTTP 요청의 ctx입니다. 클라이언트 연결 끊어지면 자동 취소됩니다 (4일차 학습 응용).

### Step 6 — main.go에서 PostgresStore 선택

```go
func main() {
    ctx := context.Background()

    var store user.Store
    dsn := os.Getenv("DATABASE_URL")
    if dsn != "" {
        pgStore, err := user.NewPostgresStore(ctx, dsn)
        if err != nil {
            slog.Error("DB 연결 실패", "err", err)
            os.Exit(1)
        }
        defer pgStore.Close()
        store = pgStore
        slog.Info("PostgreSQL 모드")
    } else {
        store = user.NewMemoryStore()
        slog.Info("인메모리 모드 (DATABASE_URL 미설정)")
    }

    // 이하 동일
    server := httpserver.New(store)
    // ...
}
```

### Step 7 — 도커 컴포즈로 통합 테스트

`docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: userapi
      POSTGRES_PASSWORD: secret
      POSTGRES_DB: userapi
    ports:
      - "5432:5432"
    volumes:
      - ./migrations:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "userapi"]
      interval: 1s
      timeout: 3s
      retries: 5

  api:
    build: .
    environment:
      DATABASE_URL: postgres://userapi:secret@postgres:5432/userapi?sslmode=disable
    ports:
      - "8080:8080"
    depends_on:
      postgres:
        condition: service_healthy
```

```bash
docker-compose up --build
```

### 통합 테스트 — `testcontainers`

실제 PostgreSQL 컨테이너로 테스트:

```go
// internal/user/postgres_test.go
package user

import (
    "context"
    "fmt"
    "testing"
    "time"

    "github.com/testcontainers/testcontainers-go"
    "github.com/testcontainers/testcontainers-go/modules/postgres"
    "github.com/testcontainers/testcontainers-go/wait"
)

func newTestStore(t *testing.T) *PostgresStore {
    t.Helper()
    ctx := context.Background()

    container, err := postgres.RunContainer(ctx,
        testcontainers.WithImage("postgres:16-alpine"),
        postgres.WithDatabase("test"),
        postgres.WithUsername("test"),
        postgres.WithPassword("test"),
        testcontainers.WithWaitStrategy(
            wait.ForLog("database system is ready to accept connections").
                WithOccurrence(2).WithStartupTimeout(30*time.Second)),
    )
    if err != nil {
        t.Fatal(err)
    }
    t.Cleanup(func() { container.Terminate(ctx) })

    dsn, err := container.ConnectionString(ctx, "sslmode=disable")
    if err != nil {
        t.Fatal(err)
    }

    store, err := NewPostgresStore(ctx, dsn)
    if err != nil {
        t.Fatal(err)
    }

    // 스키마 생성
    _, err = store.pool.Exec(ctx, `
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )`)
    if err != nil {
        t.Fatal(err)
    }
    return store
}

func TestPostgresStore_CRUD(t *testing.T) {
    if testing.Short() {
        t.Skip("통합 테스트 - short 모드에서 스킵")
    }
    store := newTestStore(t)
    ctx := context.Background()

    u := &User{Name: "Alice", Email: "a@example.com"}
    if err := store.Create(ctx, u); err != nil {
        t.Fatal(err)
    }

    got, err := store.Get(ctx, u.ID)
    if err != nil {
        t.Fatal(err)
    }
    if got.Name != "Alice" {
        t.Errorf("name = %s", got.Name)
    }
}
```

실행:
```bash
# 단위 테스트만
go test -short ./...

# 통합 테스트 포함
go test ./...
```

### 학습 포인트

1. **인터페이스의 진가** — 비즈니스 로직 코드 변경 없이 저장소 교체
2. **`pgx.ErrNoRows`** — pgx 특유의 sentinel error
3. **PgError 코드** — `errors.As`로 PostgreSQL 에러 코드 추출 (23505 = unique violation)
4. **Connection Pool** — 직접 관리할 필요 없음, `pgxpool`이 처리
5. **`testcontainers`** — 진짜 DB로 통합 테스트, mock보다 신뢰성 ↑

---

# 도전 과제 ② — JWT 인증 미들웨어

## 문제

JWT 토큰 기반 인증 미들웨어 추가. 보호된 엔드포인트는 토큰 없으면 401.

## 솔루션

### Step 1 — 의존성

```bash
go get github.com/golang-jwt/jwt/v5
```

### Step 2 — JWT 패키지 작성

`internal/auth/jwt.go`:

```go
package auth

import (
    "errors"
    "fmt"
    "time"

    "github.com/golang-jwt/jwt/v5"
)

type Manager struct {
    secret   []byte
    issuer   string
    duration time.Duration
}

type Claims struct {
    UserID int    `json:"uid"`
    Email  string `json:"email"`
    jwt.RegisteredClaims
}

func NewManager(secret, issuer string, duration time.Duration) *Manager {
    return &Manager{
        secret:   []byte(secret),
        issuer:   issuer,
        duration: duration,
    }
}

// Generate은 새 토큰을 생성한다
func (m *Manager) Generate(userID int, email string) (string, error) {
    now := time.Now()
    claims := Claims{
        UserID: userID,
        Email:  email,
        RegisteredClaims: jwt.RegisteredClaims{
            Issuer:    m.issuer,
            IssuedAt:  jwt.NewNumericDate(now),
            ExpiresAt: jwt.NewNumericDate(now.Add(m.duration)),
            NotBefore: jwt.NewNumericDate(now),
        },
    }
    token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
    return token.SignedString(m.secret)
}

// Verify는 토큰을 검증하고 클레임을 추출한다
func (m *Manager) Verify(tokenStr string) (*Claims, error) {
    var claims Claims
    token, err := jwt.ParseWithClaims(tokenStr, &claims, func(t *jwt.Token) (any, error) {
        // 알고리즘 검증 — 가장 흔한 보안 함정
        if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
            return nil, fmt.Errorf("예상치 못한 서명 알고리즘: %v", t.Header["alg"])
        }
        return m.secret, nil
    })
    if err != nil {
        return nil, err
    }
    if !token.Valid {
        return nil, errors.New("토큰이 유효하지 않음")
    }
    return &claims, nil
}
```

> **핵심 보안 포인트**: `ParseWithClaims`의 키 함수에서 **반드시 알고리즘을 검증**해야 합니다. 안 그러면 "none" 알고리즘 공격에 노출됩니다.

### Step 3 — 미들웨어

`internal/httpserver/auth_middleware.go`:

```go
package httpserver

import (
    "context"
    "net/http"
    "strings"

    "userapi/internal/auth"
)

type ctxKey string

const userCtxKey ctxKey = "auth.user"

// AuthMiddleware는 JWT를 검증하고 사용자 정보를 ctx에 주입한다
func AuthMiddleware(mgr *auth.Manager) func(http.Handler) http.Handler {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            // 헤더에서 토큰 추출
            header := r.Header.Get("Authorization")
            if header == "" {
                writeError(w, http.StatusUnauthorized, "인증 헤더 없음")
                return
            }
            parts := strings.SplitN(header, " ", 2)
            if len(parts) != 2 || parts[0] != "Bearer" {
                writeError(w, http.StatusUnauthorized, "잘못된 형식")
                return
            }

            // 검증
            claims, err := mgr.Verify(parts[1])
            if err != nil {
                writeError(w, http.StatusUnauthorized, "유효하지 않은 토큰")
                return
            }

            // ctx에 사용자 정보 주입
            ctx := context.WithValue(r.Context(), userCtxKey, claims)
            next.ServeHTTP(w, r.WithContext(ctx))
        })
    }
}

// UserFrom은 ctx에서 인증된 사용자를 추출한다
func UserFrom(ctx context.Context) (*auth.Claims, bool) {
    c, ok := ctx.Value(userCtxKey).(*auth.Claims)
    return c, ok
}
```

### Step 4 — 로그인 핸들러 + 보호된 라우트 분리

```go
// internal/httpserver/handlers.go에 추가

type LoginRequest struct {
    Email    string `json:"email"`
    Password string `json:"password"`
}

type LoginResponse struct {
    Token string `json:"token"`
}

func (s *Server) login(w http.ResponseWriter, r *http.Request) {
    var req LoginRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        writeError(w, http.StatusBadRequest, "잘못된 JSON")
        return
    }

    // 실제로는 DB에서 사용자 조회 후 bcrypt 비교
    // 데모용: 하드코딩
    if req.Email != "admin@example.com" || req.Password != "secret" {
        writeError(w, http.StatusUnauthorized, "잘못된 자격 증명")
        return
    }

    token, err := s.AuthMgr.Generate(1, req.Email)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "토큰 생성 실패")
        return
    }
    writeJSON(w, http.StatusOK, LoginResponse{Token: token})
}

// Routes 분리: 공개 / 보호
func (s *Server) Routes() http.Handler {
    public := http.NewServeMux()
    public.HandleFunc("GET /healthz", s.healthz)
    public.HandleFunc("POST /login", s.login)

    protected := http.NewServeMux()
    protected.HandleFunc("POST /users", s.createUser)
    protected.HandleFunc("GET /users", s.listUsers)
    protected.HandleFunc("GET /users/{id}", s.getUser)
    protected.HandleFunc("PUT /users/{id}", s.updateUser)
    protected.HandleFunc("DELETE /users/{id}", s.deleteUser)

    // 보호 라우트에 인증 미들웨어 적용
    authedHandler := AuthMiddleware(s.AuthMgr)(protected)

    // 통합
    mux := http.NewServeMux()
    mux.Handle("/healthz", public)
    mux.Handle("/login", public)
    mux.Handle("/users", authedHandler)
    mux.Handle("/users/", authedHandler)
    return mux
}
```

### Step 5 — Server 구조체 업데이트

```go
type Server struct {
    Store   user.Store
    AuthMgr *auth.Manager
}

func New(store user.Store, mgr *auth.Manager) *Server {
    return &Server{Store: store, AuthMgr: mgr}
}
```

### Step 6 — main.go 통합

```go
import "userapi/internal/auth"

func main() {
    // ...
    secret := os.Getenv("JWT_SECRET")
    if secret == "" {
        slog.Error("JWT_SECRET 환경 변수 필요")
        os.Exit(1)
    }
    authMgr := auth.NewManager(secret, "userapi", 24*time.Hour)

    server := httpserver.New(store, authMgr)
    // ...
}
```

### Step 7 — 테스트 (curl)

```bash
# 로그인
curl -X POST http://localhost:8080/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"secret"}'
# {"token":"eyJhbGc..."}

TOKEN="eyJhbGc..."

# 토큰 없이 — 401
curl http://localhost:8080/users
# {"error":"인증 헤더 없음"}

# 토큰 있음 — OK
curl http://localhost:8080/users -H "Authorization: Bearer $TOKEN"
```

### 학습 포인트

1. **JWT 알고리즘 검증** — 가장 흔한 보안 버그
2. **미들웨어 합성** — `AuthMiddleware(protected)` 같은 함수형 조합
3. **Context로 인증 정보 전달** — 4일차 학습 활용
4. **공개/보호 라우트 분리** — 단순한 mux 중첩으로 깔끔히 처리

---

# 도전 과제 ③ — OpenAPI / Swagger UI

## 문제

API 문서를 Swagger UI로 자동 노출.

## 솔루션 — swaggo + swag

### Step 1 — 도구 설치

```bash
go install github.com/swaggo/swag/cmd/swag@latest
go get github.com/swaggo/http-swagger/v2
go get github.com/swaggo/files
```

### Step 2 — 주석으로 문서화

`cmd/userapi/main.go` 상단에 일반 정보:

```go
// @title           User API
// @version         1.0
// @description     사용자 관리 REST API
// @host            localhost:8080
// @BasePath        /
// @securityDefinitions.apikey BearerAuth
// @in header
// @name Authorization
package main
```

각 핸들러에 주석:

```go
// CreateUser godoc
// @Summary     사용자 생성
// @Description 새 사용자 생성
// @Tags        users
// @Accept      json
// @Produce     json
// @Param       user body  user.User true "사용자 정보"
// @Success     201 {object} user.User
// @Failure     400 {object} errorResponse
// @Failure     409 {object} errorResponse
// @Security    BearerAuth
// @Router      /users [post]
func (s *Server) createUser(w http.ResponseWriter, r *http.Request) {
    // ...
}
```

### Step 3 — Swagger 핸들러 등록

```go
import (
    httpSwagger "github.com/swaggo/http-swagger/v2"
    _ "userapi/docs"  // 자동 생성될 패키지
)

func (s *Server) Routes() http.Handler {
    mux := http.NewServeMux()
    // ...
    mux.Handle("/swagger/", httpSwagger.Handler(
        httpSwagger.URL("/swagger/doc.json"),
    ))
    return mux
}
```

### Step 4 — 문서 생성

```bash
swag init -g cmd/userapi/main.go -o docs
```

생성되는 파일:
```
docs/
├── docs.go
├── swagger.json
└── swagger.yaml
```

### Step 5 — Makefile 자동화

```makefile
.PHONY: docs
docs:
	@which swag > /dev/null || go install github.com/swaggo/swag/cmd/swag@latest
	swag init -g cmd/userapi/main.go -o docs

build: docs
	go build -o bin/$(BINARY) ./cmd/$(BINARY)
```

### Step 6 — 확인

```bash
make build
./bin/userapi
```

브라우저로 `http://localhost:8080/swagger/`. **인터랙티브 API 문서**가 표시됩니다. Bearer 토큰도 입력해 직접 호출 가능.

### 학습 포인트

1. **코드 주석이 곧 문서** — Javadoc 스타일
2. **OpenAPI 표준 준수** — 다른 도구와 호환 (codegen 등)
3. **생성 자동화** — Makefile에 통합해서 빌드 시 자동 갱신

---

# 도전 과제 ④ — Prometheus 메트릭

## 문제

`/metrics` 엔드포인트에 Prometheus 형식 메트릭 노출.

## 솔루션

### Step 1 — 의존성

```bash
go get github.com/prometheus/client_golang/prometheus
go get github.com/prometheus/client_golang/prometheus/promhttp
```

### Step 2 — 메트릭 정의

`internal/metrics/metrics.go`:

```go
package metrics

import (
    "github.com/prometheus/client_golang/prometheus"
    "github.com/prometheus/client_golang/prometheus/promauto"
)

var (
    HTTPRequestsTotal = promauto.NewCounterVec(
        prometheus.CounterOpts{
            Name: "userapi_http_requests_total",
            Help: "HTTP 요청 총 수",
        },
        []string{"method", "path", "status"},
    )

    HTTPRequestDuration = promauto.NewHistogramVec(
        prometheus.HistogramOpts{
            Name:    "userapi_http_request_duration_seconds",
            Help:    "HTTP 요청 처리 시간",
            Buckets: prometheus.DefBuckets,  // 0.005~10초 기본
        },
        []string{"method", "path"},
    )

    UsersTotal = promauto.NewGauge(
        prometheus.GaugeOpts{
            Name: "userapi_users_total",
            Help: "현재 등록된 사용자 수",
        },
    )

    DBQueryDuration = promauto.NewHistogramVec(
        prometheus.HistogramOpts{
            Name: "userapi_db_query_duration_seconds",
            Help: "DB 쿼리 처리 시간",
        },
        []string{"operation"},
    )
)
```

### Step 3 — 메트릭 미들웨어

`internal/httpserver/metrics_middleware.go`:

```go
package httpserver

import (
    "net/http"
    "strconv"
    "time"

    "userapi/internal/metrics"
)

func MetricsMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        start := time.Now()
        sr := &statusRecorder{ResponseWriter: w, status: 200}

        next.ServeHTTP(sr, r)

        duration := time.Since(start).Seconds()
        path := normalizePath(r.URL.Path)  // /users/123 → /users/:id

        metrics.HTTPRequestsTotal.WithLabelValues(
            r.Method, path, strconv.Itoa(sr.status),
        ).Inc()

        metrics.HTTPRequestDuration.WithLabelValues(
            r.Method, path,
        ).Observe(duration)
    })
}

// normalizePath는 ID 같은 가변 부분을 일반화한다
func normalizePath(p string) string {
    // 실제로는 라우터에서 패턴을 가져오는 게 정확
    // 간이 구현
    if strings.HasPrefix(p, "/users/") && p != "/users/" {
        return "/users/:id"
    }
    return p
}
```

> **중요**: **path를 그대로 라벨로 쓰면 안 됩니다.** `/users/1`, `/users/2`, ... 각각이 별도 시계열을 만들어 카디널리티 폭발. 반드시 `/users/:id` 형태로 정규화.

### Step 4 — /metrics 엔드포인트 등록

```go
import "github.com/prometheus/client_golang/prometheus/promhttp"

func (s *Server) Routes() http.Handler {
    mux := http.NewServeMux()
    // ...
    mux.Handle("GET /metrics", promhttp.Handler())
    return mux
}
```

### Step 5 — DB 작업도 측정

`internal/user/postgres.go`:

```go
import "userapi/internal/metrics"

func (s *PostgresStore) Get(ctx context.Context, id int) (*User, error) {
    timer := prometheus.NewTimer(metrics.DBQueryDuration.WithLabelValues("get"))
    defer timer.ObserveDuration()

    // 기존 로직
}
```

### Step 6 — 사용자 수 게이지 업데이트

```go
func (s *PostgresStore) Create(ctx context.Context, u *User) error {
    if err := /* 생성 */; err != nil {
        return err
    }
    metrics.UsersTotal.Inc()
    return nil
}

func (s *PostgresStore) Delete(ctx context.Context, id int) error {
    if err := /* 삭제 */; err != nil {
        return err
    }
    metrics.UsersTotal.Dec()
    return nil
}
```

### Step 7 — 확인 및 Prometheus 통합

```bash
curl http://localhost:8080/metrics
```

출력:
```
# HELP userapi_http_requests_total HTTP 요청 총 수
# TYPE userapi_http_requests_total counter
userapi_http_requests_total{method="GET",path="/users",status="200"} 5
userapi_http_requests_total{method="POST",path="/users",status="201"} 3

# HELP userapi_http_request_duration_seconds HTTP 요청 처리 시간
# TYPE userapi_http_request_duration_seconds histogram
userapi_http_request_duration_seconds_bucket{method="GET",path="/users",le="0.005"} 4
userapi_http_request_duration_seconds_bucket{method="GET",path="/users",le="0.01"} 5
# ...
```

### Prometheus 통합

`prometheus.yml`:
```yaml
scrape_configs:
  - job_name: 'userapi'
    static_configs:
      - targets: ['userapi:8080']
    scrape_interval: 15s
```

### 자주 쓰는 PromQL

```promql
# 초당 요청 수
rate(userapi_http_requests_total[5m])

# 에러율
rate(userapi_http_requests_total{status=~"5.."}[5m]) /
rate(userapi_http_requests_total[5m])

# p95 응답 시간
histogram_quantile(0.95, rate(userapi_http_request_duration_seconds_bucket[5m]))

# 현재 사용자 수
userapi_users_total
```

### 학습 포인트

1. **세 가지 메트릭 타입** — Counter(누적), Gauge(현재값), Histogram(분포)
2. **카디널리티 관리** — 라벨에 무한히 다양한 값(id, IP 등) 넣지 말 것
3. **`promauto`** — 자동 등록으로 코드 간결
4. **레이블 정규화** — `/users/:id` 패턴화 필수

---

# 도전 과제 ⑤ — GitHub Actions CI/CD

## 문제

CI: 푸시 시 테스트 + 빌드. CD: 태그 푸시 시 도커 이미지 푸시.

## 솔루션

### Step 1 — CI 워크플로

`.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: '1.22'
          cache: true

      - name: Verify dependencies
        run: go mod verify

      - name: go vet
        run: go vet ./...

      - name: Format check
        run: |
          if [ -n "$(gofmt -l .)" ]; then
            echo "다음 파일이 포맷되지 않음:"
            gofmt -l .
            exit 1
          fi

      - name: Run linter
        uses: golangci/golangci-lint-action@v4
        with:
          version: latest

      - name: Run tests with race detector
        run: go test -race -coverprofile=coverage.out ./...
        env:
          DATABASE_URL: postgres://test:test@localhost:5432/test?sslmode=disable

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.out

      - name: Build
        run: go build -v ./...
```

### Step 2 — 릴리스 워크플로 (태그 푸시)

`.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: '1.22'

      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract version
        id: version
        run: echo "VERSION=${GITHUB_REF#refs/tags/v}" >> $GITHUB_OUTPUT

      - name: Build multi-arch Docker images
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          platforms: linux/amd64,linux/arm64
          tags: |
            ghcr.io/${{ github.repository }}:${{ steps.version.outputs.VERSION }}
            ghcr.io/${{ github.repository }}:latest
          build-args: |
            VERSION=${{ steps.version.outputs.VERSION }}

      - name: Build cross-platform binaries
        run: |
          mkdir -p dist
          for platform in linux/amd64 linux/arm64 darwin/amd64 darwin/arm64 windows/amd64; do
            os=$(echo $platform | cut -d/ -f1)
            arch=$(echo $platform | cut -d/ -f2)
            ext=""
            [ "$os" = "windows" ] && ext=".exe"
            output="dist/userapi-${os}-${arch}${ext}"
            GOOS=$os GOARCH=$arch go build \
              -ldflags="-s -w -X 'main.Version=${{ steps.version.outputs.VERSION }}'" \
              -o $output ./cmd/userapi
            (cd dist && tar czf userapi-${os}-${arch}.tar.gz $(basename $output))
          done

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: dist/*.tar.gz
          generate_release_notes: true
```

### Step 3 — Dockerfile 멀티 스테이지

`Dockerfile`:

```dockerfile
# === 빌드 스테이지 ===
FROM golang:1.22-alpine AS builder

ARG VERSION=dev

WORKDIR /src

# 의존성 캐시 최적화 - 먼저 go.mod만 복사
COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build \
    -ldflags="-s -w -X 'main.Version=${VERSION}'" \
    -o /out/userapi \
    ./cmd/userapi

# === 실행 스테이지 ===
FROM gcr.io/distroless/static:nonroot

COPY --from=builder /out/userapi /userapi

EXPOSE 8080 6060
USER nonroot:nonroot
ENTRYPOINT ["/userapi"]
```

> **`distroless/static:nonroot`** 사용 이유: 5MB 미만, shell 없음, root 아님 → 보안 ↑

### Step 4 — `.golangci.yml`

루트에 린터 설정:

```yaml
linters:
  enable:
    - errcheck
    - gosimple
    - govet
    - ineffassign
    - staticcheck
    - unused
    - gofmt
    - goimports
    - gocyclo
    - misspell
    - revive
    - bodyclose
    - errorlint

linters-settings:
  gocyclo:
    min-complexity: 15
  revive:
    rules:
      - name: exported

issues:
  exclude-use-default: false
```

### Step 5 — 사용 흐름

```bash
# 개발 흐름
git add .
git commit -m "feat: add user search"
git push origin develop
# → CI 자동 실행 (테스트 + 빌드)

# 릴리스 흐름
git tag v1.0.0
git push origin v1.0.0
# → 멀티 아키텍처 도커 이미지 빌드 + GitHub Container Registry 푸시
# → 멀티 플랫폼 바이너리 빌드 + GitHub Release 자동 생성
```

### 학습 포인트

1. **PR 단위 검증** — 모든 PR이 테스트/린트 통과해야 머지
2. **태그 기반 릴리스** — semver 태그가 곧 배포 트리거
3. **Distroless** — 보안과 크기 모두 잡는 베이스 이미지
4. **Multi-arch 빌드** — ARM 서버까지 한 번에 지원

---

# 도전 과제 ⑥ — 부하 테스트 + pprof 분석

## 문제

`wrk` 또는 `vegeta`로 부하를 걸고, `pprof`로 병목 분석.

## 솔루션

### Step 1 — 도구 설치

```bash
# wrk
sudo apt install wrk    # Ubuntu

# vegeta (Go로 작성됨)
go install github.com/tsenart/vegeta/v12@latest
```

### Step 2 — 서버 실행 (pprof 활성화)

5일차 7교시에서 이미 pprof 통합 완료. 6060 포트로 노출.

```bash
make run &
# 또는
./bin/userapi &
```

### Step 3 — 부하 시나리오 ① 단순 GET

```bash
# wrk: 10 스레드, 100 동시 연결, 30초간
wrk -t10 -c100 -d30s http://localhost:8080/healthz
```

출력 예시:
```
Running 30s test @ http://localhost:8080/healthz
  10 threads and 100 connections
  Thread Stats   Avg      Stdev     Max   +/- Stdev
    Latency     2.34ms  1.23ms   45.67ms   89.23%
    Req/Sec     4.32k    234.56     5.67k    73.21%
  1290847 requests in 30.00s, 156.78MB read
Requests/sec:  43028.23
Transfer/sec:      5.23MB
```

**약 43,000 RPS** — Go 표준 라이브러리만으로도 매우 좋은 성능.

### Step 4 — 부하 시나리오 ② POST (생성)

`payload.json`:
```json
{"name":"Load Test","email":"load@test.com"}
```

```bash
# vegeta로 POST 시나리오
echo "POST http://localhost:8080/users
Content-Type: application/json
@payload.json" | vegeta attack -duration=30s -rate=1000 | vegeta report
```

> **주의**: 위 시나리오는 이메일 중복으로 대부분 409 응답. 부하 측정용으로는 동적 이메일 생성 필요.

동적 생성을 위한 스크립트:

```bash
#!/bin/bash
# gen_targets.sh
for i in {1..10000}; do
  cat <<EOF
POST http://localhost:8080/users
Content-Type: application/json
@-
{"name":"User$i","email":"user$i@test.com"}

EOF
done
```

```bash
./gen_targets.sh > targets.txt
vegeta attack -duration=30s -rate=500 -targets=targets.txt | vegeta report
```

### Step 5 — 부하 중 프로파일링

부하 거는 동안 별도 터미널에서:

```bash
# CPU 프로파일 (30초)
go tool pprof http://localhost:6060/debug/pprof/profile?seconds=30
```

`pprof` 셸:
```
(pprof) top10
Showing nodes accounting for 5.20s, 65.00% of 8.00s total
      flat  flat%   sum%        cum   cum%
     1.50s 18.75% 18.75%      2.10s 26.25%  encoding/json.Marshal
     0.80s 10.00% 28.75%      0.80s 10.00%  syscall.Syscall
     0.60s  7.50% 36.25%      1.20s 15.00%  net/http.(*conn).serve
     0.50s  6.25% 42.50%      0.50s  6.25%  runtime.mallocgc
     ...

(pprof) list createUser
Total: 8.00s
ROUTINE ======================== userapi/internal/httpserver.(*Server).createUser
      40ms      2.10s (flat, cum) 26.25%
    ...
         .          .     30:	var u user.User
      40ms     2.10s     31:	if err := json.NewDecoder(r.Body).Decode(&u); err != nil {
         .          .     32:		writeError(w, ...)
    ...
```

**JSON 디코딩이 핫스팟**임을 발견. 일반적 최적화 후보:
- `json.NewDecoder(r.Body).Decode` → 더 빠른 `easyjson`/`sonic` 검토
- 결과 캐싱
- 페이지 응답 압축 (`gzip`)

### Step 6 — 메모리 프로파일

```bash
go tool pprof http://localhost:6060/debug/pprof/heap
```

```
(pprof) top10 -cum
Showing nodes accounting for 256MB, 64.00% of 400MB total
      flat  flat%   sum%        cum   cum%
       0      0% 100%      256MB 64.00%  net/http.serve
       0      0% 100%      256MB 64.00%  userapi/.../handlers.go:30
    180MB 45.00% 45.00%      180MB 45.00%  encoding/json.Unmarshal
    ...

(pprof) web
# 브라우저에서 그래프 확인
```

### Step 7 — Flame Graph로 직관 확인

```bash
go tool pprof -http=:8000 http://localhost:6060/debug/pprof/profile?seconds=30
# 브라우저 자동 열림
# 좌측 메뉴 → Flame Graph
```

**가장 넓은 막대 = CPU 가장 많이 사용**. 직관적으로 핫스팟을 찾을 수 있습니다.

### Step 8 — 고루틴 누수 확인

```bash
# 부하 멈춘 후 30초 대기
curl http://localhost:6060/debug/pprof/goroutine?debug=2 | head -100
```

같은 함수에서 멈춰 있는 고루틴이 **수백 개 이상**이라면 누수 의심.

정상 상태에서는 보통 `net/http.(*conn).serve`가 활성 연결 수만큼 있고, idle 상태에서 빠르게 감소합니다.

### Step 9 — 성능 비교 — 인메모리 vs PostgreSQL

```bash
# 인메모리 모드 (DATABASE_URL 미설정)
unset DATABASE_URL
./bin/userapi &
wrk -t4 -c50 -d20s -s post_user.lua http://localhost:8080/users
# Requests/sec: 15000+

# PostgreSQL 모드
export DATABASE_URL="postgres://..."
./bin/userapi &
wrk -t4 -c50 -d20s -s post_user.lua http://localhost:8080/users
# Requests/sec: 2000~5000 (DB가 병목)
```

**DB가 병목**일 때 다음을 검토:
1. 인덱스 추가 (email, created_at)
2. Connection Pool 크기 조정 (`MaxConns`)
3. PreparedStatement 활용
4. 읽기 복제본 분리

### Step 10 — 결과 정리 보고서 템플릿

`docs/perf-report.md`:

```markdown
# 성능 측정 보고서 (vX.Y.Z)

## 환경
- 서버: 4 vCPU / 8GB RAM
- DB: PostgreSQL 16, 동일 호스트
- Go: 1.22.0

## 시나리오별 결과

### GET /healthz (cache hit)
- RPS: 43,000
- p50: 1.8ms, p95: 4.5ms, p99: 12ms
- CPU: 60%, RAM: 80MB

### POST /users (DB write)
- RPS: 2,800
- p50: 18ms, p95: 45ms, p99: 120ms
- DB CPU: 75%

## 식별된 병목
1. JSON 디코딩 (createUser의 26%)
2. DB connection wait (3ms 평균)

## 적용한 개선
- [x] DB Pool MaxConns 10 → 25
- [x] email 인덱스 추가
- [x] gzip 압축 활성화

## 개선 후
- POST /users RPS: 2,800 → 4,200 (+50%)
```

### 학습 포인트

1. **pprof는 운영 환경에서도 안전** — 임시 sampling
2. **Flame Graph가 가장 직관적** — 넓은 막대를 찾아라
3. **부하 시나리오는 다양하게** — 단일 GET, 다양한 POST, 혼합 트래픽
4. **DB와 앱 병목 구분** — DB 메트릭(`pg_stat_*`) 함께 확인
5. **개선 → 측정 → 검증 사이클** — 추측이 아닌 측정 기반 최적화

---

# 🎯 5일차 솔루션 마무리

| 솔루션 | 핵심 학습 |
|---|---|
| PostgreSQL 연동 | 인터페이스 추상화 효과, `pgx`, testcontainers |
| JWT 인증 | 알고리즘 검증, 미들웨어 합성, ctx 기반 전달 |
| OpenAPI/Swagger | 코드 주석 → 문서, swaggo |
| Prometheus 메트릭 | Counter/Gauge/Histogram, 카디널리티 관리 |
| GitHub Actions | PR 검증, 멀티 아키텍처 빌드, distroless |
| 부하 + pprof | wrk/vegeta, Flame Graph, 측정 기반 최적화 |

---

# 🎓 5일 과정 전체 솔루션 정리

5일간 작성한 모든 코드를 종합하면, **실무에서 통할 수준의 Go 프로젝트**가 됩니다.

## 산출물 체크리스트

- [x] 단일 파일 CLI (1일차)
- [x] 멀티 패키지 프로젝트 + Makefile (2일차)
- [x] 동시성 활용 도구 (3일차 Producer-Consumer)
- [x] Context 기반 워커 풀 (4일차 healthcheck)
- [x] REST API 서버 (5일차 userapi)
- [x] DB 연동
- [x] 인증/인가
- [x] API 문서
- [x] 메트릭
- [x] CI/CD
- [x] 부하 테스트

## 한 줄 격언으로 마무리

> *"Make it work, make it right, make it fast — in that order."*
> — Kent Beck

5일간 우리는 이 순서대로 달려왔습니다. 동작하는 코드를 만들고(1~2일), 올바르게 다듬고(3~4일), 그리고 측정해서 빠르게 만들었습니다(5일차 도전 ⑥).

이제 여러분의 차례입니다. 사내 도구 하나라도 **Go로 옮겨보세요.** 작게 시작해서 점점 늘리면 6개월 후 완전히 다른 개발자가 되어 있을 겁니다.

**Happy Gophering!** 🐹
