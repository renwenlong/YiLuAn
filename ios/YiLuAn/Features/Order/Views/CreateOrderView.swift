import SwiftUI

struct CreateOrderView: View {
    @StateObject private var viewModel = OrderViewModel()
    @Environment(\.dismiss) private var dismiss

    @State private var selectedService: ServiceType?
    @State private var hospitalId = ""
    @State private var hospitalName = ""
    @State private var appointmentDate = Date()
    @State private var appointmentTime = "09:00"
    @State private var description = ""
    @State private var step = 1

    private let timeSlots = (8...17).flatMap { hour in
        ["00", "30"].map { min in String(format: "%02d:%@", hour, min) }
    }

    var body: some View {
        NavigationStack {
            VStack {
                // Step indicator
                HStack {
                    ForEach(1...4, id: \.self) { s in
                        Circle()
                            .fill(s <= step ? Color.blue : Color(.systemGray4))
                            .frame(width: 8, height: 8)
                        if s < 4 {
                            Rectangle()
                                .fill(s < step ? Color.blue : Color(.systemGray4))
                                .frame(height: 2)
                        }
                    }
                }
                .padding()

                // Step content
                Group {
                    switch step {
                    case 1: serviceSelectionStep
                    case 2: hospitalSelectionStep
                    case 3: dateTimeStep
                    case 4: confirmStep
                    default: EmptyView()
                    }
                }
                .frame(maxHeight: .infinity)

                // Navigation buttons
                HStack {
                    if step > 1 {
                        Button("上一步") { step -= 1 }
                            .buttonStyle(.bordered)
                    }
                    Spacer()
                    if step < 4 {
                        Button("下一步") { nextStep() }
                            .buttonStyle(.borderedProminent)
                            .disabled(!canProceed)
                    } else {
                        Button("提交订单") {
                            Task { await submitOrder() }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(viewModel.isLoading)
                    }
                }
                .padding()
            }
            .navigationTitle("创建订单")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private var serviceSelectionStep: some View {
        VStack(spacing: 16) {
            Text("选择服务类型")
                .font(.headline)
            ForEach(ServiceType.allCases, id: \.rawValue) { service in
                Button {
                    selectedService = service
                } label: {
                    HStack {
                        VStack(alignment: .leading) {
                            Text(service.displayName)
                                .font(.headline)
                            Text("¥\(service.price as NSDecimalNumber)")
                                .font(.subheadline)
                                .foregroundStyle(.orange)
                        }
                        Spacer()
                        if selectedService == service {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundStyle(.blue)
                        }
                    }
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(12)
                }
                .buttonStyle(.plain)
            }
        }
        .padding()
    }

    private var hospitalSelectionStep: some View {
        VStack(spacing: 16) {
            Text("选择医院")
                .font(.headline)
            if hospitalName.isEmpty {
                Text("请在首页搜索并选择医院")
                    .foregroundStyle(.secondary)
            } else {
                Text(hospitalName)
                    .font(.title3)
                    .padding()
                    .frame(maxWidth: .infinity)
                    .background(Color(.systemGray6))
                    .cornerRadius(12)
            }
        }
        .padding()
    }

    private var dateTimeStep: some View {
        VStack(spacing: 16) {
            Text("选择预约时间")
                .font(.headline)

            DatePicker("日期", selection: $appointmentDate, displayedComponents: .date)
                .datePickerStyle(.graphical)

            Picker("时间", selection: $appointmentTime) {
                ForEach(timeSlots, id: \.self) { slot in
                    Text(slot).tag(slot)
                }
            }
            .pickerStyle(.wheel)
            .frame(height: 100)
        }
        .padding()
    }

    private var confirmStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("确认订单")
                .font(.headline)

            VStack(alignment: .leading, spacing: 12) {
                confirmRow("服务类型", selectedService?.displayName ?? "")
                confirmRow("医院", hospitalName)
                confirmRow("日期", dateString)
                confirmRow("时间", appointmentTime)
                confirmRow("费用", "¥\(selectedService?.price as? NSDecimalNumber ?? 0)")
                if !description.isEmpty {
                    confirmRow("备注", description)
                }
            }
            .padding()
            .background(Color(.systemGray6))
            .cornerRadius(12)

            TextField("备注（可选）", text: $description, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(3...6)

            if let error = viewModel.errorMessage {
                Text(error)
                    .foregroundStyle(.red)
                    .font(.caption)
            }
        }
        .padding()
    }

    private func confirmRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label)
                .foregroundStyle(.secondary)
                .frame(width: 80, alignment: .leading)
            Text(value)
            Spacer()
        }
        .font(.subheadline)
    }

    private var canProceed: Bool {
        switch step {
        case 1: return selectedService != nil
        case 2: return !hospitalId.isEmpty
        case 3: return true
        default: return true
        }
    }

    private func nextStep() {
        if canProceed { step += 1 }
    }

    private var dateString: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: appointmentDate)
    }

    private func submitOrder() async {
        guard let service = selectedService else { return }
        let order = await viewModel.createOrder(
            serviceType: service,
            hospitalId: hospitalId,
            date: dateString,
            time: appointmentTime,
            description: description.isEmpty ? nil : description
        )
        if order != nil {
            dismiss()
        }
    }
}
