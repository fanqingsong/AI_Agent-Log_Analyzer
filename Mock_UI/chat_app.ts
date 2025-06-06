// BIG FAT WARNING: to avoid the complexity of npm, this typescript is compiled in the browser
// there's currently no static type checking

// @ts-ignore
import { marked } from 'https://cdnjs.cloudflare.com/ajax/libs/marked/15.0.0/lib/marked.esm.js'

interface Message {
  role: string
  content: string
  timestamp: string
  chatId: string
}

interface Chat {
  id: string
  title: string
  messages: Message[]
  lastTimestamp: string
  createdAt: string
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
    toggleModelMenu: () => void;
    selectModel: (model: string) => void;
    setTheme: (theme: 'light' | 'dark') => void;
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

  private generateChatId(): string {
    return `chat-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`
  }

  private async loadChats() {
    const response = await fetch('/chat/')
    const messages = await response.json() as Message[]
    
    // Sort messages by timestamp first
    messages.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())

    // Group messages by time proximity (messages within 5 minutes go to the same chat)
    let currentChatId: string | null = null
    let lastMessageTime: number = 0
    const CHAT_TIME_GAP = 5 * 60 * 1000 // 5 minutes in milliseconds

    messages.forEach(msg => {
      const messageTime = new Date(msg.timestamp).getTime()
      
      // Start new chat if:
      // 1. No current chat
      // 2. Time gap is too large
      // 3. Previous message was from AI and current is from user
      if (!currentChatId || 
          messageTime - lastMessageTime > CHAT_TIME_GAP ||
          (this.chats.get(currentChatId)?.messages.slice(-1)[0]?.role === 'assistant' && msg.role === 'user')) {
        currentChatId = `chat-${messageTime}`
        this.chats.set(currentChatId, {
          id: currentChatId,
          title: '',
          messages: [],
          lastTimestamp: msg.timestamp,
          createdAt: msg.timestamp
        })
      }

      if (currentChatId) {
        const chat = this.chats.get(currentChatId)
        if (chat) {
          // Add chatId to message
          msg.chatId = currentChatId
          chat.messages.push(msg)
          
          // Update title if this is the first user message
          if (!chat.title && msg.role === 'user') {
            chat.title = this.generateChatTitle(msg)
          }
          
          // Update timestamps
          if (msg.timestamp > chat.lastTimestamp) {
            chat.lastTimestamp = msg.timestamp
          }
          lastMessageTime = messageTime
        }
      }
    })

    // Clean up empty chats
    for (const [id, chat] of this.chats.entries()) {
      if (chat.messages.length === 0) {
        this.chats.delete(id)
      }
    }

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

  private formatTime(dateStr: string): string {
    const date = new Date(dateStr)
    return date.toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit',
      hour12: false 
    })
  }

  private renderChatHistory() {
    if (!this.chatHistory) return
    
    this.chatHistory.innerHTML = ''

    // Group chats by date using createdAt
    const chatsByDate = new Map<string, Chat[]>()
    
    Array.from(this.chats.values())
      .sort((a, b) => b.lastTimestamp.localeCompare(a.lastTimestamp))
      .forEach(chat => {
        const date = new Date(chat.createdAt).toLocaleDateString()
        if (!chatsByDate.has(date)) {
          chatsByDate.set(date, [])
        }
        chatsByDate.get(date)?.push(chat)
      })

    // Sort dates in reverse chronological order
    const sortedDates = Array.from(chatsByDate.keys())
      .sort((a, b) => new Date(b).getTime() - new Date(a).getTime())

    // Render groups
    sortedDates.forEach(date => {
      const chats = chatsByDate.get(date)
      if (!chats || chats.length === 0) return

      const group = document.createElement('div')
      group.className = 'chat-history-group'

      const dateHeader = document.createElement('div')
      dateHeader.className = 'chat-history-date'
      
      // Split date into weekday and date parts
      const [weekday, dateStr] = this.formatDate(date).split(' ')
      dateHeader.innerHTML = `${weekday} <span>${dateStr}</span>`
      
      group.appendChild(dateHeader)

      // Sort chats within the group by last message time
      chats.sort((a, b) => new Date(b.lastTimestamp).getTime() - new Date(a.lastTimestamp).getTime())
        .forEach(chat => {
          if (chat.messages.length === 0) return

          const div = document.createElement('div')
          div.className = `chat-history-item ${chat.id === this.currentChatId ? 'active' : ''}`
          
          const contentWrapper = document.createElement('div')
          contentWrapper.className = 'chat-content'
          contentWrapper.onclick = () => this.switchChat(chat.id)
          
          const titleRow = document.createElement('div')
          titleRow.className = 'title-row'
          
          const title = document.createElement('div')
          title.className = 'title'
          title.textContent = chat.title || 'New Chat'
          
          const time = document.createElement('div')
          time.className = 'chat-time'
          time.textContent = this.formatTime(chat.lastTimestamp)
          
          titleRow.appendChild(title)
          titleRow.appendChild(time)
          contentWrapper.appendChild(titleRow)
          div.appendChild(contentWrapper)

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
          group.appendChild(div)
        })

      if (group.children.length > 1) { // Only add group if it has chats (>1 because of dateHeader)
        this.chatHistory.appendChild(group)
      }
    })
  }

  private formatDate(dateStr: string): string {
    const date = new Date(dateStr)
    
    // Get weekday name
    const weekday = date.toLocaleDateString('en-US', { weekday: 'long' })
    
    // Format date as DD.MM.YYYY
    const day = date.getDate().toString().padStart(2, '0')
    const month = (date.getMonth() + 1).toString().padStart(2, '0')
    const year = date.getFullYear()
    
    return `${weekday} ${day}.${month}.${year}`
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

    const chatId = this.generateChatId()
    const timestamp = new Date().toISOString()
    
    this.chats.set(chatId, {
      id: chatId,
      title: 'New Chat',
      messages: [],
      lastTimestamp: timestamp,
      createdAt: timestamp
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
    
    if (!this.currentChatId) {
      this.createNewChat()
    }

    this.spinner.classList.add('active')
    const formData = new FormData(e.target as HTMLFormElement)
    formData.append('model', this.currentModel)
    formData.append('chatId', this.currentChatId!) // Add chatId to request
    
    console.log('Submitting with chatId:', this.currentChatId)
    this.promptInput.value = ''
    this.promptInput.disabled = true

    try {
      const response = await fetch('/chat/', { method: 'POST', body: formData })
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
          // Temporary fix: use current chatId if message doesn't have one
          if (!msg.chatId && this.currentChatId) {
            msg.chatId = this.currentChatId
            console.log('Added chatId to new message:', msg)
          }

          this.renderMessage(msg)
          if (msg.chatId) {
            const chat = this.chats.get(msg.chatId)
            if (chat) {
              chat.messages.push(msg)
              if (msg.timestamp > chat.lastTimestamp) {
                chat.lastTimestamp = msg.timestamp
              }
              // Update title only for the first message in chat
              if (chat.title === 'New Chat' && msg.role === 'user') {
                chat.title = this.generateChatTitle(msg)
                console.log('Updated chat title for new message:', chat.title)
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