const SERVICE_TYPES = {
  full_accompany: { label: '全程陪诊', price: 299, icon: 'full', desc: '挂号、候诊、就诊、取药全流程陪同' },
  half_accompany: { label: '半程陪诊', price: 199, icon: 'half', desc: '陪同就诊或取报告，按需半程服务' },
  errand: { label: '代办跑腿', price: 149, icon: 'errand', desc: '代取报告、代挂号、代取药等跑腿服务' },
}

const ORDER_STATUS = {
  created: { label: '待接单', color: '#FAAD14' },
  accepted: { label: '已接单', color: '#1890FF' },
  in_progress: { label: '进行中', color: '#1890FF' },
  completed: { label: '已完成', color: '#52C41A' },
  reviewed: { label: '已评价', color: '#52C41A' },
  cancelled_by_patient: { label: '患者取消', color: '#FF4D4F' },
  cancelled_by_companion: { label: '陪诊师取消', color: '#FF4D4F' },
  rejected_by_companion: { label: '陪诊师拒单', color: '#FF4D4F' },
  expired: { label: '已过期', color: '#999999' },
}

const USER_ROLES = {
  patient: '患者',
  companion: '陪诊师',
}

module.exports = { SERVICE_TYPES, ORDER_STATUS, USER_ROLES }
