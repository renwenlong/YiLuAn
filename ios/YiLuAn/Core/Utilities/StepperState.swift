import Foundation

/// U-1 折叠式分步下单「状态机 + 回改冲突判定」纯逻辑真源（iOS 端）
///
/// 真源：`docs/design/wireframes/U1-folding-stepper/README.md` §四 状态机 / §五 边界态
/// **与微信端 `wechat/utils/stepperState.js` 逐字符等价互锁**（AC#25 必测）：
/// - 步骤数、步骤命名、isStepFilled / computeStepStates / canSubmit /
///   firstIncompleteStep / canNavigateTo / checkDepartmentConflict /
///   departmentConflictToast 全部行为对齐
///
/// 步骤（钉死 4 步，不可拆分/合并）：
///   1 服务类型  2 医院  3 日期  4 患者&陪诊师确认
///
/// 步骤三态：
///   - `.collapsed` 未到（点击无响应，除非已 done）
///   - `.active`    当前展开编辑
///   - `.done`      已完成，显摘要，可点回改
enum StepState: String, Equatable {
    case collapsed
    case active
    case done
}

/// 页面数据快照（双端字段名同源）。UI 仅消费 read-only 视图，不直接 mutate 此结构。
struct StepperData: Equatable {
    var serviceType: String?
    var hospitalId: String?
    var date: String?       // "YYYY-MM-DD"
    var period: String?     // "上午" | "下午"
    var department: String? // 可选，回改冲突判定用

    init(
        serviceType: String? = nil,
        hospitalId: String? = nil,
        date: String? = nil,
        period: String? = nil,
        department: String? = nil
    ) {
        self.serviceType = serviceType
        self.hospitalId = hospitalId
        self.date = date
        self.period = period
        self.department = department
    }
}

/// 科室冲突判定结果
struct DepartmentConflict: Equatable {
    let conflict: Bool
    let clearedDept: String?

    static let none = DepartmentConflict(conflict: false, clearedDept: nil)

    static func cleared(_ dept: String) -> DepartmentConflict {
        DepartmentConflict(conflict: true, clearedDept: dept)
    }
}

enum StepperState {
    /// 步骤数固定 4（钉死，与微信 STEP_TITLES.length 互锁）
    static let totalSteps: Int = 4

    /// 步骤命名（i18n: 与微信 createOrder.step* 同源 key，AC#25 契约演进为同源字典语义等价）。
    /// static var computed 每次访问走 loc.t，切语言实时（同 003B-5 FamilyRelation 模式）。
    static var stepTitles: [String] {
        let loc = LocalizationManager.shared
        return [
            loc.t("createOrder.stepService"),
            loc.t("createOrder.stepHospital"),
            loc.t("createOrder.stepDate"),
            loc.t("createOrder.stepPatient"),
        ]
    }

    /// 各步骤「是否已填」判定。
    /// 注意：科室(department)为可选，不参与第②步完成判定（与微信端 isStepFilled 同源）。
    static func isStepFilled(_ step: Int, data: StepperData) -> Bool {
        switch step {
        case 1:
            return !(data.serviceType?.isEmpty ?? true)
        case 2:
            return !(data.hospitalId?.isEmpty ?? true)
        case 3:
            return !(data.date?.isEmpty ?? true) && !(data.period?.isEmpty ?? true)
        case 4:
            // 患者(本人或家人均可)恒成立；陪诊师可选。第④步「确认」即完成。
            return true
        default:
            return false
        }
    }

    /// 计算每个步骤的三态。
    ///
    /// - `currentStep`：当前 active 的步骤序号(1..4)。
    /// - `maxReachedStep`：用户曾到达的最大步序(1..4)，决定哪些步已「访问过」。
    ///                    省略时默认等于 currentStep（首次线性前进场景）。
    ///
    /// 规则：
    ///   - `= current`                         → `.active`
    ///   - 已访问过(s <= maxReached) 且已填    → `.done`
    ///   - 其余                                 → `.collapsed`
    ///
    /// 回改场景：current 指回某 done 步，maxReached 不回退，下游已填步保持 done。
    static func computeStepStates(
        currentStep: Int,
        data: StepperData,
        maxReachedStep: Int? = nil
    ) -> [StepState] {
        let maxReached = maxReachedStep ?? currentStep
        var states: [StepState] = []
        for s in 1...totalSteps {
            if s == currentStep {
                states.append(.active)
            } else if s <= maxReached && isStepFilled(s, data: data) {
                // 已访问过且已填 → done（回改时下游保留）
                states.append(.done)
            } else {
                states.append(.collapsed)
            }
        }
        return states
    }

    /// 是否可点击进入某步（回改）：该步已 done 才可点。
    static func canNavigateTo(_ step: Int, data: StepperData) -> Bool {
        step != 0 && isStepFilled(step, data: data)
    }

    /// 全部 4 步是否都已填（可提交）。
    static func canSubmit(_ data: StepperData) -> Bool {
        for s in 1...totalSteps where !isStepFilled(s, data: data) {
            return false
        }
        return true
    }

    /// 第一个未完成步（用于置灰提交时滚动定位）。返回 1..4，全完成返回 0。
    static func firstIncompleteStep(_ data: StepperData) -> Int {
        for s in 1...totalSteps where !isStepFilled(s, data: data) {
            return s
        }
        return 0
    }

    /// 回改医院后科室冲突判定（钉死规则，§四 回改冲突判定）。
    ///
    /// - `oldDepartment`: 原选科室名（可空）
    /// - `newDeptList`:   新院区科室名数组
    ///
    /// 返回：
    ///   - `.none`                          无冲突（未选 or 仍存在）
    ///   - `.cleared("神经内科")`          冲突，需清空 + toast
    static func checkDepartmentConflict(
        oldDepartment: String?,
        newDeptList: [String]
    ) -> DepartmentConflict {
        let dept = (oldDepartment ?? "").trimmingCharacters(in: .whitespaces)
        if dept.isEmpty {
            return .none // 原未选科室 → 无冲突
        }
        if newDeptList.contains(dept) {
            return .none // 仍存在 → 保留
        }
        return .cleared(dept) // 不存在 → 清空
    }

    /// 科室冲突 toast 文案（i18n: stepper.deptConflictToast，插值 {dept}）。
    static func departmentConflictToast(clearedDept: String) -> String {
        LocalizationManager.shared.t("stepper.deptConflictToast", clearedDept)
    }
}
