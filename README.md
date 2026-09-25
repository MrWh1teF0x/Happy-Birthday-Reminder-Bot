# Happy-Birthday-Reminder-Bot
Телеграмм бот для отправки уведомлений о том, что скоро день рождения у какого-то человека

## Запуск

Прод: `docker compose up -d --build`

Дев (код с хоста, автоперезапуск бота при изменениях, пересборка не нужна):
`docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build`
