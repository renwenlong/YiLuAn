import SwiftUI

struct ChatRoomView: View {
    let orderId: String
    let currentUserId: String
    @StateObject private var viewModel = ChatViewModel()
    @State private var inputText = ""

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 12) {
                        ForEach(viewModel.messages) { message in
                            ChatBubbleView(
                                message: message,
                                isMe: message.senderId == currentUserId
                            )
                            .id(message.id)
                        }
                    }
                    .padding()
                }
                .onChange(of: viewModel.messages.count) {
                    if let last = viewModel.messages.last {
                        withAnimation {
                            proxy.scrollTo(last.id, anchor: .bottom)
                        }
                    }
                }
            }

            Divider()

            HStack(spacing: 12) {
                TextField("输入消息...", text: $inputText)
                    .textFieldStyle(.roundedBorder)

                Button {
                    let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !text.isEmpty else { return }
                    inputText = ""
                    Task {
                        await viewModel.sendMessage(orderId: orderId, content: text)
                    }
                } label: {
                    Image(systemName: "paperplane.fill")
                        .foregroundColor(.blue)
                }
                .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding()
        }
        .navigationTitle("聊天")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await viewModel.loadMessages(orderId: orderId)
            await viewModel.connectWebSocket(orderId: orderId)
            await viewModel.markRead(orderId: orderId)
        }
        .onDisappear {
            Task { await viewModel.disconnectWebSocket() }
        }
    }
}

struct ChatBubbleView: View {
    let message: ChatMessage
    let isMe: Bool

    var body: some View {
        HStack {
            if isMe { Spacer() }
            VStack(alignment: isMe ? .trailing : .leading, spacing: 4) {
                if message.type == .image {
                    AsyncImage(url: URL(string: message.content)) { image in
                        image.resizable().scaledToFit()
                    } placeholder: {
                        ProgressView()
                    }
                    .frame(maxWidth: 200, maxHeight: 200)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                } else {
                    Text(message.content)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(isMe ? Color.blue : Color(.systemGray5))
                        .foregroundColor(isMe ? .white : .primary)
                        .clipShape(RoundedRectangle(cornerRadius: 16))
                }
            }
            if !isMe { Spacer() }
        }
    }
}
