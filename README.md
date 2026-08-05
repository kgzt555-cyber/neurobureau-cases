# neurobureau — кейсы

Демонстрационные работы: боты, автоматизации и обработка данных.
Каждая папка — отдельный кейс с README, кодом и результатом прогона.

- [parser-catalog](parser-catalog/) — парсер каталога товаров в таблицу Excel:
  1000 позиций за 104 секунды, цена числом, автофильтр

Основные работы живут отдельно:

- Бот-визитка с ИИ — [@neurobur_bot](https://t.me/neurobur_bot)
- Mini App «Витрина» — [kgzt555-cyber.github.io/neurobureau](https://kgzt555-cyber.github.io/neurobureau/)
- Их исходники — [github.com/kgzt555-cyber/neurobureau](https://github.com/kgzt555-cyber/neurobureau)

## Запуск

Общее окружение на все кейсы:

    python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/python -m pytest

Все кейсы сделаны как демонстрация подхода — реальных клиентов за ними нет.
Написать: [@kafka_q](https://t.me/kafka_q)
