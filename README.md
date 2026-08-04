# Postwise

Postwise is an AI assistant for your email. It reads your inbox, sorts it, chats with you about it, and can reply for you. It runs on your own computer, so your mail stays private.

![The Postwise app](docs/hero.png)

## Chat with your inbox

Talk to your email like you would to a person. Ask a question and Postwise answers using your real messages, and it points you to the ones it used. Tell it to star, label, mark as read, or archive, and it just does it. Ask it to reply and it writes a draft, ready for you to send.

![Chatting with the inbox](docs/chat.gif)

## Write and send

Reply to a message or start a brand new one. You can write it yourself, or describe what you want in a sentence and let Postwise draft it. Nothing ever goes out until you press send.

![Writing a new email](docs/compose.png)

## What it does

- Sorts every email into groups like work, personal, receipts, and spam.
- Lets you chat with your inbox in plain words, and take actions like starring, labeling, and archiving.
- Drafts and sends replies, and writes brand new emails too.
- Lets you make your own colored labels and asks the assistant to file mail into them.
- Catches emails that try to trick the AI, and never follows instructions hidden inside a message.
- Shows your emails with their real look and formatting.
- Pulls in new mail on its own, and marks things as read in Gmail when you read them.
- Comes in light or dark mode, with fonts and a logo you can pick.

## How it works

You connect your Gmail once. Postwise pulls your mail into a small database on your computer and sorts it. When you chat, ask a question, or draft a reply, that runs on a local model through Ollama, so your email never leaves your machine. Sending a reply or marking mail as read are the only things that touch Gmail, and sending always waits for your ok.

## Run it

You need Python, Node, and Ollama installed.

First time setup:

```bash
uv sync --extra dev --extra gmail --extra web --extra desktop
ollama pull llama3.2
```

Open it as a desktop app:

```bash
DESKTOP=1 npm --prefix web run build
uv run postwise app
```

Or run it in your browser instead:

```bash
uv run postwise serve
```

```bash
npm --prefix web run dev
```

Then open http://localhost:3000. The first time you sync, a browser opens so you can connect your Gmail.

## Privacy

Your real mail and login stay in files on your computer that are never shared. The chat and drafting use a local model, so your email is never sent to a cloud service. Postwise treats every email as untrusted, so a message can never make the assistant do something you did not ask for.

Want more detail on the safety design? See [THREAT_MODEL.md](THREAT_MODEL.md).
