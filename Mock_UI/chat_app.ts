// BIG FAT WARNING: to avoid the complexity of npm, this typescript is compiled in the browser
// there's currently no static type checking

// @ts-ignore
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

interface ChatAppInterface {
  deleteChat: (chatId: string) => void;
  toggleModelMenu: () => void;
  selectModel: (model: string) => void;
  setTheme: (theme: 'light' | 'dark') => void;
}

declare global {
  interface Window {
    chatApp: ChatAppInterface;
  }
}

class ChatApp implements ChatAppInterface {
  private convElement: HTMLElement
  private promptInput: HTMLInputElement
  private spinner: HTMLElement
  private chatHistory: HTMLElement
  private chats: Map<string, Chat> = new Map()
  private currentChatId: string | null = null
  private currentModel: string = 'openai'

  constructor() {
    const convEl = document.getElementById('conversation')
    const promptEl = document.getElementById('prompt-input')
    const spinnerEl = document.getElementById('spinner')
    const historyEl = document.getElementById('chat-history')

    if (!convEl || !promptEl || !spinnerEl || !historyEl) {
      throw new Error('Required DOM elements not found')
    }

    this.convElement = convEl
    this.promptInput = promptEl as HTMLInputElement
    this.spinner = spinnerEl
    this.chatHistory = historyEl

    this.initEventListeners()
    this.loadChats()
    this.initModelSelector()
    this.initThemeToggle()
  }

  private initEventListeners() {
    const form = document.querySelector('form')
    const newChatBtn = document.getElementById('new-chat')
    
    if (form) {
      form.addEventListener('submit', (e) => this.onSubmit(e).catch(this.onError))
    }
    
    if (newChatBtn) {
      newChatBtn.addEventListener('click', () => this.createNewChat())
    }
    
    // Close menus when clicking outside
    document.addEventListener('click', (e) => {
      const target = e.target as Element
      if (!target.closest('.chat-menu') && !target.closest('.chat-menu-button')) {
        document.querySelectorAll('.chat-menu.show').forEach(menu => {
          menu.classList.remove('show')
        })
      }
      if (!target.closest('.model-menu') && !target.closest('.model-selector')) {
        document.querySelectorAll('.model-menu.show').forEach(menu => {
          menu.classList.remove('show')
        })
      }
    })
  }

  private initModelSelector() {
    window.toggleModelMenu = this.toggleModelMenu.bind(this)
    window.selectModel = this.selectModel.bind(this)
  }

  private initThemeToggle() {
    window.setTheme = this.setTheme.bind(this)
    
    // Set initial theme
    const savedTheme = localStorage.getItem('theme') as 'light' | 'dark' || 'light'
    this.setTheme(savedTheme)
  }

  private generateChatId(date: Date = new Date()): string {
    return `${date.toLocaleDateString()}-${date.getHours()}-${date.getMinutes()}-${date.getSeconds()}-${date.getMilliseconds()}`
  }

  private async loadChats() {
    const response = await fetch('/chat/')
    const messages = await response.json() as Message[]

    // Group messages by conversation using timestamp as base for chat ID
    messages.forEach(msg => {
      const date = new Date(msg.timestamp)
      const chatId = this.generateChatId(date)
      
      if (!this.chats.has(chatId)) {
        this.chats.set(chatId, {
          id: chatId,
          title: this.generateChatTitle(msg),
          messages: [],
          lastTimestamp: msg.timestamp
        })
      }
      const chat = this.chats.get(chatId)
      if (chat) {
        chat.messages.push(msg)
        // Update last timestamp if this message is newer
        if (msg.timestamp > chat.lastTimestamp) {
          chat.lastTimestamp = msg.timestamp
        }
      }
    })

    this.renderChatHistory()
    if (this.chats.size > 0) {
      const latestChat = Array.from(this.chats.values())
        .sort((a, b) => b.lastTimestamp.localeCompare(a.lastTimestamp))[0]
      this.switchChat(latestChat.id)
    }
  }

  private generateChatTitle(firstMsg: Message): string {
    // Remove markdown symbols and limit to first sentence or N characters
    const cleanContent = firstMsg.content
      .replace(/[#*`]/g, '') // Remove markdown symbols
      .trim()
    
    // Try to get first sentence (end with . ! or ?)
    const sentenceMatch = cleanContent.match(/^[^.!?]+[.!?]/)
    if (sentenceMatch) {
      const sentence = sentenceMatch[0].trim()
      return sentence.length > 50 ? sentence.slice(0, 47) + '...' : sentence
    }
    
    // If no sentence found, just take first N characters
    return cleanContent.length > 50 ? cleanContent.slice(0, 47) + '...' : cleanContent
  }

  private renderChatHistory() {
    if (!this.chatHistory) return
    
    this.chatHistory.innerHTML = ''
    Array.from(this.chats.values())
      .sort((a, b) => b.lastTimestamp.localeCompare(a.lastTimestamp))
      .forEach(chat => {
        const div = document.createElement('div')
        div.className = `chat-history-item ${chat.id === this.currentChatId ? 'active' : ''}`
        
        const title = document.createElement('div')
        title.className = 'title'
        title.textContent = chat.title
        title.onclick = () => this.switchChat(chat.id)
        div.appendChild(title)

        const menuButton = document.createElement('button')
        menuButton.className = 'chat-menu-button'
        menuButton.innerHTML = '<i class="bi bi-three-dots-vertical"></i>'
        menuButton.onclick = (e) => {
          e.stopPropagation()
          this.toggleChatMenu(chat.id)
        }
        div.appendChild(menuButton)

        const menu = document.createElement('div')
        menu.className = 'chat-menu'
        menu.setAttribute('data-chat-id', chat.id)
        menu.innerHTML = `
          <div class="chat-menu-item delete" onclick="event.stopPropagation(); window.chatApp.deleteChat('${chat.id}');">
            <i class="bi bi-trash"></i>
            Delete chat
          </div>
        `
        div.appendChild(menu)

        this.chatHistory?.appendChild(div)
      })
  }

  private toggleChatMenu(chatId: string) {
    // Close all other menus first
    document.querySelectorAll('.chat-menu.show').forEach(menu => {
      if (menu.getAttribute('data-chat-id') !== chatId) {
        menu.classList.remove('show')
      }
    })

    // Toggle current menu
    const menu = document.querySelector(`.chat-menu[data-chat-id="${chatId}"]`)
    if (menu) {
      menu.classList.toggle('show')
    }
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

  private cleanupEmptyChats() {
    for (const [chatId, chat] of this.chats.entries()) {
      if (chat.messages.length === 0 && chat.title === 'New Chat') {
        this.chats.delete(chatId)
      }
    }
    this.renderChatHistory()
  }

  private createNewChat() {
    // Cleanup any empty chats before creating a new one
    this.cleanupEmptyChats()

    const date = new Date()
    const chatId = this.generateChatId(date)
    this.chats.set(chatId, {
      id: chatId,
      title: 'New Chat',
      messages: [],
      lastTimestamp: date.toISOString()
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
    body.append('model', this.currentModel) // Add selected model to the request
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
    if (!response.ok || !response.body) {
      throw new Error(`Unexpected response: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let text = ''

    try {
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
            if (chat) {
              chat.messages.push(msg)
              if (msg.timestamp > chat.lastTimestamp) {
                chat.lastTimestamp = msg.timestamp
              }
              // Update title only for the first message in chat
              if (chat.messages.length === 1 && chat.title === 'New Chat') {
                chat.title = this.generateChatTitle(msg)
                this.renderChatHistory()
              }
            }
          }
        })
      }
    } catch (error) {
      console.error('Error processing response:', error)
    } finally {
      this.spinner.classList.remove('active')
      this.promptInput.disabled = false
      this.promptInput.focus()
    }
  }

  private onError(error: any) {
    console.error(error)
    document.getElementById('error')?.classList.remove('d-none')
    this.spinner.classList.remove('active')
  }

  public deleteChat(chatId: string): void {
    this.chats.delete(chatId)
    if (this.currentChatId === chatId) {
      if (this.chats.size > 0) {
        const latestChat = Array.from(this.chats.values())
          .sort((a, b) => b.lastTimestamp.localeCompare(a.lastTimestamp))[0]
        this.switchChat(latestChat.id)
      } else {
        this.currentChatId = null
        this.convElement.innerHTML = ''
      }
    }
    this.renderChatHistory()
  }

  public toggleModelMenu(): void {
    const menu = document.querySelector('.model-menu') as HTMLElement
    menu.classList.toggle('show')
  }

  public selectModel(model: string): void {
    this.currentModel = model
    const currentModelSpan = document.querySelector('.current-model') as HTMLElement
    currentModelSpan.textContent = model.charAt(0).toUpperCase() + model.slice(1)
    this.toggleModelMenu()
  }

  public setTheme(theme: 'light' | 'dark'): void {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }
}

// Initialize the app
const chatApp = new ChatApp()
window.chatApp = chatApp