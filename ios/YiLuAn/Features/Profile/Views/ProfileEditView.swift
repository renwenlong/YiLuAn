import SwiftUI
import PhotosUI

struct ProfileEditView: View {
    @EnvironmentObject var authViewModel: AuthViewModel
    @StateObject private var viewModel = ProfileViewModel()
    @EnvironmentObject var loc: LocalizationManager
    @State private var selectedItem: PhotosPickerItem?
    @State private var displayName: String = ""
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        Form {
            // Avatar section
            Section {
                HStack {
                    Spacer()
                    VStack(spacing: 8) {
                        avatarView
                        PhotosPicker(
                            selection: $selectedItem,
                            matching: .images,
                            photoLibrary: .shared()
                        ) {
                            Text(loc.t("profile.updateAvatar"))
                                .font(.footnote)
                        }
                    }
                    Spacer()
                }
                .listRowBackground(Color.clear)
            }

            // Display name
            Section(loc.t("companion.basicInfo")) {
                HStack {
                    Text(loc.t("profileSetup.nickname"))
                    Spacer()
                    TextField(loc.t("profileSetup.inputNicknameToast"), text: $displayName)
                        .multilineTextAlignment(.trailing)
                }
            }

            // Role-specific profile links
            Section(loc.t("profile.details")) {
                if authViewModel.currentUser?.role == .patient {
                    NavigationLink(loc.t("companionOrderDetail.patientInfo")) {
                        PatientProfileEditView()
                    }
                    // F-05: 代他人下单
                    NavigationLink(loc.t("profile.menuFamily")) {
                        FamilyMembersView()
                    }
                } else if authViewModel.currentUser?.role == .companion {
                    NavigationLink(loc.t("orderDetail.companionInfo")) {
                        CompanionProfileEditView()
                    }
                }
            }

            // Save
            Section {
                Button(action: {
                    Task { await save() }
                }) {
                    HStack {
                        Spacer()
                        if viewModel.isLoading {
                            ProgressView()
                        } else {
                            Text(loc.t("common.save"))
                        }
                        Spacer()
                    }
                }
                .disabled(viewModel.isLoading)
            }
        }
        .navigationTitle(loc.t("profile.menuEdit"))
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            displayName = authViewModel.currentUser?.displayName ?? ""
        }
        .onChange(of: selectedItem) { newItem in
            guard let newItem else { return }
            Task { await handleImageSelection(newItem) }
        }
        .alert(loc.t("dialog.tip"), isPresented: .init(
            get: { viewModel.errorMessage != nil },
            set: { if !$0 { viewModel.errorMessage = nil } }
        )) {
            Button(loc.t("companion.ok"), role: .cancel) {}
        } message: {
            Text(viewModel.errorMessage ?? "")
        }
    }

    @ViewBuilder
    private var avatarView: some View {
        if viewModel.isUploadingAvatar {
            ProgressView()
                .frame(width: 80, height: 80)
        } else if let urlString = authViewModel.currentUser?.avatarUrl,
                  let url = URL(string: urlString) {
            AsyncImage(url: url) { image in
                image
                    .resizable()
                    .scaledToFill()
            } placeholder: {
                ProgressView()
            }
            .frame(width: 80, height: 80)
            .clipShape(Circle())
        } else {
            Image(systemName: "person.circle.fill")
                .font(.system(size: 60))
                .foregroundStyle(.gray)
                .frame(width: 80, height: 80)
        }
    }

    private func handleImageSelection(_ item: PhotosPickerItem) async {
        guard let data = try? await item.loadTransferable(type: Data.self) else { return }
        if let avatarUrl = await viewModel.uploadAvatar(imageData: data) {
            // Refresh user to pick up new avatar
            await authViewModel.fetchCurrentUser()
        }
    }

    private func save() async {
        viewModel.displayName = displayName
        if let updatedUser = await viewModel.updateDisplayName() {
            authViewModel.currentUser = updatedUser
            dismiss()
        }
    }
}

#Preview {
    NavigationStack {
        ProfileEditView()
            .environmentObject(AuthViewModel())
    }
}
