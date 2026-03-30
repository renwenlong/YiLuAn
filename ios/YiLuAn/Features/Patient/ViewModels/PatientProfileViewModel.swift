import SwiftUI

@MainActor
class PatientProfileViewModel: ObservableObject {
    @Published var profile: PatientProfile?
    @Published var emergencyContact: String = ""
    @Published var emergencyPhone: String = ""
    @Published var medicalNotes: String = ""
    @Published var preferredHospitalId: String = ""
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var isSaved = false
    @Published var hospitals: [Hospital] = []

    func loadProfile() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let loaded: PatientProfile = try await APIClient.shared.request(.patientProfile)
            profile = loaded
            emergencyContact = loaded.emergencyContact ?? ""
            emergencyPhone = loaded.emergencyPhone ?? ""
            medicalNotes = loaded.medicalNotes ?? ""
            preferredHospitalId = loaded.preferredHospitalId ?? ""
        } catch {
            // Profile may not exist yet — that's fine; user will create it on save
            errorMessage = nil
        }
    }

    func loadHospitals() async {
        do {
            hospitals = try await APIClient.shared.request(.hospitals)
        } catch {
            // Non-fatal: hospital list is optional
        }
    }

    func saveProfile() async {
        isLoading = true
        errorMessage = nil
        isSaved = false
        defer { isLoading = false }

        do {
            let body = UpdatePatientProfileRequest(
                emergencyContact: emergencyContact.isEmpty ? nil : emergencyContact,
                emergencyPhone: emergencyPhone.isEmpty ? nil : emergencyPhone,
                medicalNotes: medicalNotes.isEmpty ? nil : medicalNotes,
                preferredHospitalId: preferredHospitalId.isEmpty ? nil : preferredHospitalId
            )
            profile = try await APIClient.shared.request(
                .updatePatientProfile,
                body: body
            )
            isSaved = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
