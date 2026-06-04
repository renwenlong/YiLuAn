import SwiftUI

/// U-1 折叠式分步下单（iOS / S2-INT-004 AC#25）
///
/// 与微信端 `wechat/pages/patient/create-order/index.wxml` **逐字符互锁**：
/// - 4 步：① 服务类型 ② 医院 ③ 日期 ④ 患者&陪诊师确认
/// - 三态：collapsed（未到，灰）/ active（当前展开 body）/ done（显摘要，可点回改）
/// - 状态机由 `StepperState` 提供唯一真源
/// - 摘要由 `OrderSummary` 提供（与微信逐字符一致）
/// - 巨字号由 `FontScale` 提供 token（@AppStorage("huge_font") 持久化）
/// - submit 按钮 sticky 底部，置灰条件 = `!StepperState.canSubmit(data)`
struct CreateOrderView: View {
    @StateObject private var viewModel = OrderViewModel()
    @Environment(\.dismiss) private var dismiss

    // MARK: - State

    @AppStorage("huge_font") private var hugeFont: Bool = false

    @State private var selectedService: ServiceType?
    // S2-REQ-003-P5c: 动态服务档位 (onAppear 拉 /public/service-packages)
    @State private var servicePackages: [ServicePackage] = ServicePackagesService.fallbackPackages
    @State private var servicePackagesIsFallback: Bool = true
    @State private var selectedPackageCode: String?
    @State private var hospitalId = ""
    @State private var hospitalName = ""
    @State private var hospitalSearchText = ""
    @State private var isSearchingHospitals = false

    // 科室（可选，§二 钉死规则——回改医院冲突时清空）
    @State private var department: String = ""
    @State private var departmentList: [String] = []

    // 日期 + 时段（与微信 period 同源）
    @State private var appointmentDate = Date()
    @State private var period: String = "上午"

    @State private var description = ""

    // 家人 picker
    @State private var familyMembers: [FamilyMember] = []
    @State private var selectedFamilyMemberId: String?

    // U-1 折叠状态机
    @State private var currentStep: Int = 1
    @State private var maxReachedStep: Int = 1

    // 回改弹框
    @State private var navigateBackTargetStep: Int? = nil

    // 当前 user 缓存（摘要患者用，本人路径）
    @State private var currentUserName: String = "本人"
    @State private var currentUserAge: Int? = nil

    // MARK: - Derived

    /// 当前 page data → StepperState/OrderSummary 输入
    private var stepperData: StepperData {
        StepperData(
            serviceType: selectedService?.rawValue,
            hospitalId: hospitalId.isEmpty ? nil : hospitalId,
            date: dateString,
            period: period,
            department: department.isEmpty ? nil : department
        )
    }

    private var stepStates: [StepState] {
        StepperState.computeStepStates(
            currentStep: currentStep,
            data: stepperData,
            maxReachedStep: maxReachedStep
        )
    }

    private var tokens: FontScaleTokens {
        FontScale.tokens(huge: hugeFont)
    }

    private var canSubmit: Bool {
        StepperState.canSubmit(stepperData)
    }

    /// "YYYY-MM-DD"，与微信 date 字段同源
    private var dateString: String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: appointmentDate)
    }

    // MARK: - Body

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // 巨字号 toggle（PRD §F5）
                hugeFontToggle

                ScrollView {
                    VStack(spacing: 16) {
                        // ① 服务类型
                        stepSection(
                            stepIndex: 1,
                            summary: OrderSummary.summaryService(
                                serviceName: selectedService?.displayName,
                                price: selectedService?.price
                            )
                        ) {
                            serviceSelectionBody
                        }

                        // ② 医院
                        stepSection(
                            stepIndex: 2,
                            summary: OrderSummary.summaryHospital(
                                hospitalName: hospitalName,
                                department: department
                            )
                        ) {
                            hospitalSelectionBody
                        }

                        // ③ 日期
                        stepSection(
                            stepIndex: 3,
                            summary: OrderSummary.summaryDate(
                                dateStr: dateString,
                                period: period
                            )
                        ) {
                            dateTimeBody
                        }

                        // ④ 患者&陪诊师确认
                        stepSection(
                            stepIndex: 4,
                            summary: OrderSummary.summaryPatient(
                                patientName: currentUserName,
                                relation: selectedFamilyMemberId == nil ? "本人" : familyRelation(),
                                age: currentUserAge
                            )
                        ) {
                            confirmBody
                        }
                    }
                    .padding()
                }

                submitArea
            }
            .navigationTitle("创建订单")
            .navigationBarTitleDisplayMode(.inline)
            .phoneRequiredAlert($viewModel.phoneRequiredMessage)
            .task {
                await loadFamilyMembers()
                await loadCurrentUser()
                await loadServicePackages()
            }
            .alert(
                "是否回改？",
                isPresented: Binding(
                    get: { navigateBackTargetStep != nil },
                    set: { if !$0 { navigateBackTargetStep = nil } }
                ),
                presenting: navigateBackTargetStep
            ) { step in
                Button("取消", role: .cancel) { navigateBackTargetStep = nil }
                Button("确认") {
                    currentStep = step
                    navigateBackTargetStep = nil
                }
            } message: { _ in
                Text("下游已选数据将保留")
            }
        }
    }

    // MARK: - Step Section（折叠容器）

    @ViewBuilder
    private func stepSection<Body: View>(
        stepIndex: Int,
        summary: String,
        @ViewBuilder body: () -> Body
    ) -> some View {
        let state = stepStates[stepIndex - 1]
        VStack(alignment: .leading, spacing: 0) {
            stepHead(stepIndex: stepIndex, state: state, summary: summary)
                .contentShape(Rectangle())
                .onTapGesture { handleStepTap(stepIndex) }

            if state == .active {
                Divider()
                    .padding(.top, tokens.labelMarginTop)
                body()
                    .padding(.top, tokens.labelMarginTop)
            }
        }
        .padding(tokens.labelMarginTop)
        .background(
            state == .done ? Color(red: 0.97, green: 0.99, blue: 1.0)
            : Color(.systemBackground)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(state == .active ? Color.blue : Color.clear, lineWidth: 2)
        )
        .cornerRadius(12)
        .opacity(state == .collapsed ? 0.6 : 1.0)
    }

    private func stepHead(stepIndex: Int, state: StepState, summary: String) -> some View {
        HStack(spacing: 12) {
            stepNumCircle(stepIndex: stepIndex, state: state)
            Text(StepperState.stepTitles[stepIndex - 1])
                .font(.system(size: tokens.bodyFont, weight: .semibold))
            Spacer(minLength: 8)
            if state == .done, !summary.isEmpty {
                Text(summary)
                    .font(.system(size: tokens.metaFont))
                    .foregroundStyle(.secondary)
                    .lineLimit(tokens.summaryClamp)
                    .multilineTextAlignment(.trailing)
            } else if state == .collapsed {
                Text("未选择")
                    .font(.system(size: tokens.metaFont))
                    .foregroundStyle(Color(.tertiaryLabel))
            }
        }
    }

    private func stepNumCircle(stepIndex: Int, state: StepState) -> some View {
        ZStack {
            Circle()
                .fill(
                    state == .done ? Color.green
                    : state == .active ? Color.blue
                    : Color(.systemGray3)
                )
                .frame(width: tokens.stepNum, height: tokens.stepNum)
            if state == .done {
                Image(systemName: "checkmark")
                    .font(.system(size: tokens.stepNum * 0.55, weight: .bold))
                    .foregroundStyle(.white)
            } else {
                Text("\(stepIndex)")
                    .font(.system(size: tokens.stepNum * 0.6, weight: .bold))
                    .foregroundStyle(.white)
            }
        }
    }

    // MARK: - Step Tap / Next

    private func handleStepTap(_ stepIndex: Int) {
        guard stepIndex != currentStep else { return }
        // 只有 done 步可回改
        if StepperState.canNavigateTo(stepIndex, data: stepperData) {
            navigateBackTargetStep = stepIndex
        }
    }

    private func advanceToNextStep() {
        guard StepperState.isStepFilled(currentStep, data: stepperData) else { return }
        let next = min(currentStep + 1, StepperState.totalSteps)
        currentStep = next
        maxReachedStep = max(maxReachedStep, next)
    }

    // MARK: - 巨字号 toggle

    private var hugeFontToggle: some View {
        HStack {
            Spacer()
            Text("巨字号")
                .font(.system(size: tokens.metaFont))
                .foregroundStyle(.secondary)
            Toggle("", isOn: $hugeFont)
                .labelsHidden()
                .tint(.blue)
        }
        .padding(.horizontal, tokens.labelMarginTop)
        .padding(.vertical, tokens.labelMarginBottom)
    }

    // MARK: - Step 1 body：服务类型

    private var serviceSelectionBody: some View {
        VStack(spacing: 8) {
            if servicePackagesIsFallback {
                Text("服务列表已降级，使用默认 3 档")
                    .font(.system(size: tokens.bodyFont * 0.85))
                    .foregroundStyle(.orange)
                    .padding(.bottom, 4)
            }
            ForEach(servicePackages) { pkg in
                Button {
                    selectedPackageCode = pkg.code
                    selectedService = ServiceType(rawValue: pkg.code)
                } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(pkg.name)
                                .font(.system(size: tokens.bodyFont, weight: .medium))
                                .foregroundStyle(.primary)
                            Spacer()
                            Text("¥\(NSDecimalNumber(decimal: pkg.price).intValue)")
                                .font(.system(size: tokens.bodyFont, weight: .semibold))
                                .foregroundStyle(.blue)
                            if selectedPackageCode == pkg.code {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(.blue)
                            }
                        }
                        // S2-REQ-003-P5b fix #4: description 渲染 (与微信端一致)
                        if let desc = pkg.description, !desc.isEmpty {
                            Text(desc)
                                .font(.system(size: tokens.bodyFont * 0.8))
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding()
                    .background(
                        selectedPackageCode == pkg.code
                            ? Color.blue.opacity(0.1)
                            : Color(.systemGray6)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(
                                selectedService == service ? Color.blue : Color.clear,
                                lineWidth: 2
                            )
                    )
                    .cornerRadius(12)
                }
                .buttonStyle(.plain)
            }
            stepNextButton
        }
    }

    // MARK: - Step 2 body：医院 + 科室

    private var hospitalSelectionBody: some View {
        VStack(spacing: 12) {
            HStack {
                TextField("搜索医院名称", text: $hospitalSearchText)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: tokens.bodyFont))
                Button {
                    isSearchingHospitals = true
                    Task {
                        await viewModel.searchHospitals(keyword: hospitalSearchText)
                        isSearchingHospitals = false
                    }
                } label: {
                    Image(systemName: "magnifyingglass")
                        .padding(8)
                        .background(Color.blue)
                        .foregroundStyle(.white)
                        .cornerRadius(8)
                }
                .disabled(hospitalSearchText.isEmpty)
            }

            if !hospitalName.isEmpty {
                HStack {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                    Text(hospitalName).font(.system(size: tokens.bodyFont, weight: .semibold))
                    Spacer()
                    Button("更换") {
                        hospitalId = ""
                        hospitalName = ""
                        departmentList = []
                        department = ""
                    }
                    .font(.system(size: tokens.metaFont))
                }
                .padding()
                .background(Color.green.opacity(0.1))
                .cornerRadius(8)

                // 科室（可选）
                if !departmentList.isEmpty {
                    Picker("科室（可选）", selection: $department) {
                        Text("不选择科室").tag("")
                        ForEach(departmentList, id: \.self) { d in
                            Text(d).tag(d)
                        }
                    }
                    .pickerStyle(.menu)
                    .font(.system(size: tokens.bodyFont))
                }
            }

            if isSearchingHospitals {
                ProgressView()
            } else if hospitalId.isEmpty {
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(viewModel.hospitals) { hospital in
                            hospitalRow(hospital: hospital)
                        }
                    }
                }
                .frame(maxHeight: 260)
            }

            stepNextButton
        }
    }

    private func hospitalRow(hospital: Hospital) -> some View {
        Button {
            handleHospitalSelect(hospital: hospital)
        } label: {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(hospital.name)
                        .font(.system(size: tokens.bodyFont, weight: .semibold))
                        .foregroundStyle(.primary)
                    if let addr = hospital.address {
                        Text(addr)
                            .font(.system(size: tokens.metaFont))
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer()
            }
            .padding()
            .background(Color(.systemGray6))
            .cornerRadius(8)
        }
        .buttonStyle(.plain)
    }

    /// 选医院 → 拉科室列表 → 回改冲突判定
    private func handleHospitalSelect(hospital: Hospital) {
        let oldHospitalId = hospitalId
        let oldDept = department

        hospitalId = hospital.id
        hospitalName = hospital.name

        // TODO: 真接口拉科室列表（待后端 endpoint，本 PR 用空数组占位避免假数据）
        // 实际效果：departmentList 暂为空，picker 不显示 —— 不阻塞主路径
        let newDeptList: [String] = []
        departmentList = newDeptList

        // 回改科室冲突判定（仅当真换了医院）
        if !oldHospitalId.isEmpty, oldHospitalId != hospital.id {
            let conflict = StepperState.checkDepartmentConflict(
                oldDepartment: oldDept,
                newDeptList: newDeptList
            )
            if conflict.conflict, let cleared = conflict.clearedDept {
                department = ""
                // toast 文案钉死（与微信端逐字符一致）
                viewModel.errorMessage = StepperState.departmentConflictToast(clearedDept: cleared)
            }
        }
    }

    // MARK: - Step 3 body：日期 + 时段

    private var dateTimeBody: some View {
        VStack(spacing: 12) {
            DatePicker(
                "日期",
                selection: $appointmentDate,
                displayedComponents: .date
            )
            .datePickerStyle(.compact)
            .font(.system(size: tokens.bodyFont))

            HStack {
                Text("时段")
                    .font(.system(size: tokens.bodyFont))
                    .foregroundStyle(.secondary)
                Spacer()
                ForEach(["上午", "下午"], id: \.self) { p in
                    Button(p) {
                        period = p
                    }
                    .padding(.horizontal, 24)
                    .padding(.vertical, 8)
                    .background(period == p ? Color.blue.opacity(0.1) : Color(.systemGray6))
                    .foregroundStyle(period == p ? Color.blue : .primary)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(period == p ? Color.blue : Color.clear, lineWidth: 2)
                    )
                    .cornerRadius(8)
                    .font(.system(size: tokens.bodyFont, weight: period == p ? .semibold : .regular))
                }
            }

            stepNextButton
        }
    }

    // MARK: - Step 4 body：患者 + 陪诊师 + 备注

    private var confirmBody: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 8) {
                Text("给谁下单")
                    .font(.system(size: tokens.bodyFont))
                    .foregroundStyle(.secondary)
                Picker("给谁下单", selection: $selectedFamilyMemberId) {
                    Text("本人").tag(String?.none)
                    ForEach(familyMembers) { m in
                        Text("\(m.name)（\(m.relationLabel)）").tag(String?.some(m.id))
                    }
                }
                .pickerStyle(.menu)
            }
            .padding()
            .background(Color(.systemGray6))
            .cornerRadius(12)

            TextField("备注（可选）", text: $description, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(3...6)
                .font(.system(size: tokens.bodyFont))

            if let error = viewModel.errorMessage {
                Text(error)
                    .foregroundStyle(.red)
                    .font(.system(size: tokens.metaFont))
            }
        }
    }

    // MARK: - 「下一步」按钮（各 active 步底部）

    private var stepNextButton: some View {
        Button {
            advanceToNextStep()
        } label: {
            Text("下一步")
                .font(.system(size: tokens.bodyFont, weight: .semibold))
                .frame(maxWidth: .infinity)
                .frame(height: tokens.primaryBtnH)
                .background(
                    StepperState.isStepFilled(currentStep, data: stepperData)
                        ? Color.blue : Color(.systemGray4)
                )
                .foregroundStyle(.white)
                .cornerRadius(12)
        }
        .disabled(!StepperState.isStepFilled(currentStep, data: stepperData))
        .padding(.top, tokens.labelMarginTop)
    }

    // MARK: - 底部 sticky 提交区

    private var submitArea: some View {
        VStack(spacing: 0) {
            Divider()
            Button {
                Task { await submitOrder() }
            } label: {
                Text(buildSubmitButtonText())
                    .font(.system(size: tokens.bodyFont, weight: .semibold))
                    .frame(maxWidth: .infinity)
                    .frame(height: tokens.primaryBtnH)
                    .background(canSubmit && !viewModel.isLoading ? Color.blue : Color(.systemGray3))
                    .foregroundStyle(.white)
                    .cornerRadius(12)
            }
            .disabled(!canSubmit || viewModel.isLoading)
            .padding()
        }
        .background(.thinMaterial)
    }

    private func buildSubmitButtonText() -> String {
        var s = "确认下单"
        if let svc = selectedService {
            s += " ¥\(NSDecimalNumber(decimal: svc.price).intValue)"
        }
        return s
    }

    // MARK: - 数据加载

    private func loadFamilyMembers() async {
        if let list = try? await FamilyMembersService.list() {
            familyMembers = list
        }
    }

    private func loadCurrentUser() async {
        // 本人路径下，从已登录 user 信息填充摘要患者
        // 占位实现：当前 ViewModel 无 currentUser；正式接入待后端 me 端点。
        // 不阻塞 stepper 状态机（patientName 为空摘要返回空串，第④步 isStepFilled 仍恒 true）
    }

    /// S2-REQ-003-P5c: 拉服务档位。Never throws——API 失败时温柔应用 fallback (acceptance #4)。
    @MainActor
    private func loadServicePackages() async {
        let packages = await ServicePackagesService.shared.list()
        servicePackages = packages
        servicePackagesIsFallback = packages.first?.isFallback ?? false
        // 如预选了 type 从 URL，sync selectedPackageCode
        if let preselected = selectedService {
            selectedPackageCode = preselected.rawValue
        }
    }

    private func familyRelation() -> String {
        guard let id = selectedFamilyMemberId,
              let m = familyMembers.first(where: { $0.id == id })
        else { return "" }
        return m.relationLabel
    }

    // MARK: - 提交

    private func submitOrder() async {
        guard let service = selectedService else { return }
        let appointmentTime = "\(period) "
        let order = await viewModel.createOrder(
            serviceType: service,
            hospitalId: hospitalId,
            date: dateString,
            time: appointmentTime,
            description: description.isEmpty ? nil : description,
            familyMemberId: selectedFamilyMemberId
        )
        if order != nil {
            dismiss()
        }
    }
}
