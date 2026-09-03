# Правила безопасности Firestore

Лайки хранятся в Firestore. Ключ в `docs/firebase-config.js` публичный —
так и задумано, он не секрет: доступ ограничивают не ключом, а правилами
на стороне Firebase. Сейчас правила не настроены, то есть коллекцию
`likes` может переписать кто угодно, у кого открыт сайт.

## Что вставить

Firebase Console → ваш проект → **Firestore Database** → вкладка
**Rules** → заменить содержимое и нажать **Publish**:

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // Лайки: документ на пару «пользователь + картина».
    // Читать может кто угодно — счётчик виден всем.
    // Писать только вошедший, только от своего имени и только
    // в документ со своим идентификатором.
    match /likes/{likeId} {
      allow read: if true;

      allow create: if request.auth != null
                    && likeId == request.auth.uid + '_' + request.resource.data.postId
                    && request.resource.data.userId == request.auth.uid
                    && request.resource.data.keys().hasOnly(['userId', 'postId', 'createdAt']);

      allow delete: if request.auth != null
                    && resource.data.userId == request.auth.uid;

      allow update: if false;      // лайк не меняют, его ставят и снимают
    }

    // Всё остальное закрыто
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

## Если структура документов другая

Правила выше рассчитаны на документы вида
`likes/<uid>_<postId>` с полями `userId`, `postId`, `createdAt`.
Посмотрите в консоли, как на самом деле выглядят ваши записи
(Firestore Database → Data), и поправьте имена полей — остальная
логика не изменится.

Проверить, не сломались ли лайки, можно там же: вкладка **Rules** →
**Rules Playground**.
