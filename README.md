---
title: Bayer FHN Quiz
emoji: 🎮
colorFrom: green
colorTo: blue
sdk: streamlit
sdk_version: "1.40.0"
app_file: app.py
pinned: false
short_description: Temporary Bayer FHN product quiz for external testers
---

# Bayer FHN Quiz

임시 외부 배포용 제품 학습 퀴즈입니다. 결과는 Supabase `quiz_results`에 저장됩니다.

## Space Secrets

Hugging Face Space Settings → Secrets에 아래 값을 넣습니다.

- `POSTGRES_HOST`
- `POSTGRES_PORT` (`5432`)
- `POSTGRES_DB` (`postgres`)
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_SSLMODE` (`require`)
