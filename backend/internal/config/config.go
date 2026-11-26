package config

import (
	"fmt"
	"net"
	"net/url"

	"github.com/ilyakaznacheev/cleanenv"
)

type HTTPServerConfig struct {
	Host string `env:"HTTP_HOST" env-default:"127.0.0.1"`
	Port int    `env:"HTTP_PORT" env-default:"8080"`
}

type PostgresConfig struct {
	Host     string `env:"POSTGRES_HOST" env-default:"localhost"`
	Port     int    `env:"POSTGRES_PORT" env-default:"5432"`
	User     string `env:"POSTGRES_USER" env-default:"postgres"`
	Password string `env:"POSTGRES_PASSWORD" env-default:"postgres"`
	DBName   string `env:"POSTGRES_DB" env-default:"project_memory"`
	SSLMode  string `env:"DB_SSL_MODE" env-default:"disable"`
}

type S3Config struct {
	S3Endpoint         string `env:"S3_ENDPOINT" env-default:"http://localhost:9000"`
	S3Region           string `env:"S3_REGION" env-default:"us-east-1"`
	S3Bucket           string `env:"S3_BUCKET" env-required:"true"`
	S3AccessKey        string `env:"S3_ACCESS_KEY" env-required:"true"`
	S3SecretKey        string `env:"S3_SECRET_KEY" env-required:"true"`
	S3PresignTTLSecond int    `env:"S3_PRESIGN_TTL_SECOND" env-default:"900"`
}

type KafkaConfig struct {
	KafkaBrokers string `env:"KAFKA_BROKERS" env-default:"localhost:9092"`
	KafkaTopic   string `env:"KAFKA_TOPIC" env-default:"meetings.processing"`
}

type Config struct {
	HTTP     HTTPServerConfig
	Postgres PostgresConfig
	S3       S3Config
	Kafka    KafkaConfig
}

func Load() (*Config, error) {
	var cfg Config

	err := cleanenv.ReadConfig("../.env", &cfg)
	if err != nil {
		err = cleanenv.ReadEnv(&cfg)
		if err != nil {
			return nil, fmt.Errorf("load configuration: %w", err)
		}
	}

	if cfg.HTTP.Port < 1 || cfg.HTTP.Port > 65535 {
		return nil, fmt.Errorf("HTTP_PORT must be between 1 and 65535")
	}
	if cfg.Postgres.Host == "" || cfg.Postgres.DBName == "" || cfg.Postgres.User == "" {
		return nil, fmt.Errorf("postgres host, database name, and user must be configured")
	}
	if cfg.Postgres.Port < 1 || cfg.Postgres.Port > 65535 {
		return nil, fmt.Errorf("POSTGRES_PORT must be between 1 and 65535")
	}
	if cfg.S3.S3PresignTTLSecond < 1 {
		return nil, fmt.Errorf("S3_PRESIGN_TTL_SECOND must be positive")
	}

	return &cfg, nil
}

func (c PostgresConfig) DSN() string {
	u := &url.URL{
		Scheme: "postgres",
		User:   url.UserPassword(c.User, c.Password),
		Host:   net.JoinHostPort(c.Host, fmt.Sprintf("%d", c.Port)),
		Path:   "/" + c.DBName,
	}
	query := url.Values{}
	query.Set("sslmode", c.SSLMode)
	u.RawQuery = query.Encode()
	return u.String()
}
