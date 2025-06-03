// BIG FAT WARNING: to avoid the complexity of npm, this typescript is compiled in the browser
// there's currently no static type checking

import { marked } from 'https://cdnjs.cloudflare.com/ajax/libs/marked/15.0.0/lib/marked.esm.js'

interface Message {
  role: string
  content: string
  timestamp: string
}

interface Chat {
  id: string
  title: string
  messages: Message[]
  lastTimestamp: string
}

class ChatApp {
  private convElement = document.getElementById('conversation')
  private promptInput = document.getElementById('prompt-input') as HTMLInputElement
  private spinner = document.getElementById('spinner')
  private chatHistory = document.getElementById('chat-history')
  private chats: Map<string, Chat> = new Map()
  private currentChatId: string | null = null

  constructor() {
    this.initEventListeners()
    this.loadChats()
  }

  private initEventListeners() {
    document.querySelector('form').addEventListener('submit', (e) => this.onSubmit(e).catch(this.onError))
    document.getElementById('new-chat').addEventListener('click', () => this.createNewChat())
  }

  private async loadChats() {
    const response = await fetch('/chat/')
    const text = await response.text()
    const messages = text.split('\n')
      .filter(line => line.length > 1)
      .map(j => JSON.parse(j)) as Message[]

    // Group messages by chat (using date as chat ID)
    messages.forEach(msg => {
      const chatId = new Date(msg.timestamp).toLocaleDateString()
      if (!this.chats.has(chatId)) {
        this.chats.set(chatId, {
          id: chatId,
          title: this.generateChatTitle(msg),
          messages: [],
          lastTimestamp: msg.timestamp
        })
      }
      this.chats.get(chatId).messages.push(msg)
    })

    this.renderChatHistory()
    if (this.chats.size > 0) {
      const latestChat = Array.from(this.chats.values())
        .sort((a, b) => b.lastTimestamp.localeCompare(a.lastTimestamp))[0]
      this.switchChat(latestChat.id)
    }
  }

  private generateChatTitle(firstMsg: Message): string {
    return firstMsg.content.slice(0, 30) + '...'
  }

  private renderChatHistory() {
    this.chatHistory.innerHTML = ''
    Array.from(this.chats.values())
      .sort((a, b) => b.lastTimestamp.localeCompare(a.lastTimestamp))
      .forEach(chat => {
        const div = document.createElement('div')
        div.className = `chat-history-item ${chat.id === this.currentChatId ? 'active' : ''}`
        div.textContent = chat.title
        div.onclick = () => this.switchChat(chat.id)
        this.chatHistory.appendChild(div)
      })
  }

  private switchChat(chatId: string) {
    this.currentChatId = chatId
    this.convElement.innerHTML = ''
    const chat = this.chats.get(chatId)
    if (chat) {
      chat.messages.forEach(msg => this.renderMessage(msg))
      this.renderChatHistory()
    }
  }

  private createNewChat() {
    const chatId = new Date().toLocaleDateString()
    this.chats.set(chatId, {
      id: chatId,
      title: 'New Chat',
      messages: [],
      lastTimestamp: new Date().toISOString()
    })
    this.switchChat(chatId)
  }

  private renderMessage(message: Message) {
    const { timestamp, role, content } = message
    const id = `msg-${timestamp}`
    let msgDiv = document.getElementById(id)
    if (!msgDiv) {
      msgDiv = document.createElement('div')
      msgDiv.id = id
      msgDiv.title = `${role} at ${timestamp}`
      msgDiv.classList.add('border-top', 'pt-2', role)
      this.convElement.appendChild(msgDiv)
    }
    msgDiv.innerHTML = marked.parse(content)
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })
  }

  private async onSubmit(e: SubmitEvent) {
    e.preventDefault()
    this.spinner.classList.add('active')
    const body = new FormData(e.target as HTMLFormElement)
    this.promptInput.value = ''
    this.promptInput.disabled = true

    try {
      const response = await fetch('/chat/', { method: 'POST', body })
      await this.onFetchResponse(response)
    } catch (error) {
      this.onError(error)
    }
  }

  private async onFetchResponse(response: Response) {
    if (!response.ok) {
      throw new Error(`Unexpected response: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let text = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      
      text += decoder.decode(value)
      const messages = text.split('\n')
        .filter(line => line.length > 1)
        .map(j => JSON.parse(j)) as Message[]
      
      messages.forEach(msg => {
        this.renderMessage(msg)
        if (this.currentChatId) {
          const chat = this.chats.get(this.currentChatId)
          chat.messages.push(msg)
          chat.lastTimestamp = msg.timestamp
          if (chat.title === 'New Chat') {
            chat.title = this.generateChatTitle(msg)
            this.renderChatHistory()
          }
        }
      })
    }

    this.spinner.classList.remove('active')
    this.promptInput.disabled = false
    this.promptInput.focus()
  }

  private onError(error: any) {
    console.error(error)
    document.getElementById('error').classList.remove('d-none')
    this.spinner.classList.remove('active')
  }
}

new ChatApp()