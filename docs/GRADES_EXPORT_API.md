# 成绩导出功能 API 文档

## 概述

本文档描述了MCQ系统中的成绩导出功能，包括批量导出ZIP和汇总表导出DOCX两个核心功能。

## 功能说明

### 1. 导出ZIP（批量成绩报告）

**功能描述**：将指定试卷的所有考生成绩报告导出为ZIP压缩包，每个考生一个独立的DOCX文件。

**适用场景**：
- 需要为每个学生提供详细的个人成绩报告
- 需要存档所有学生的完整答题记录
- 需要批量分发个人成绩报告

**导出内容**：
- 每个DOCX文件包含：
  - 学生ID
  - 试卷名称
  - 考试时间（开始/结束）
  - 总分
  - 每道题的详细答题情况（题目、选项、标准答案、学生答案、判定结果、解析）

### 2. 导出DOCX（成绩汇总表）

**功能描述**：生成一个包含所有考生答题情况和总得分的汇总表格。

**适用场景**：
- 需要快速查看所有学生的成绩概况
- 需要进行成绩统计分析
- 需要生成班级成绩报告

**导出内容**：
- 试卷基本信息（名称、考试人数）
- 成绩汇总表格：
  - 列：学生ID | Q1 | Q2 | ... | Qn | 总分
  - 每题显示：学生答案 + 正确/错误标记（✓/✗）
- 统计信息：
  - 平均分
  - 最高分
  - 最低分

## API 接口

### 1. 导出ZIP

**接口地址**：`GET /mcq_public/grades/export_zip`

**请求参数**：
- `paper_id` (string, required): 试卷ID（文件名，如 "试卷_1234567890.docx"）

**请求示例**：
```
GET /mcq_public/grades/export_zip?paper_id=测试试卷_1234567890.docx
```

**响应**：
- 成功：返回ZIP文件流（application/zip）
- 失败：返回JSON错误信息
  ```json
  {
    "ok": false,
    "msg": "该试卷暂无已完成的考试记录"
  }
  ```

**文件命名规则**：
- ZIP文件名：`{试卷名称}_成绩报告_{时间戳}.zip`
- 内部DOCX文件名：`成绩报告_{学生ID}_{attempt_id前8位}.docx`

### 2. 导出成绩汇总DOCX

**接口地址**：`GET /mcq_public/grades/export_summary_docx`

**请求参数**：
- `paper_id` (string, required): 试卷ID（文件名，如 "试卷_1234567890.docx"）

**请求示例**：
```
GET /mcq_public/grades/export_summary_docx?paper_id=测试试卷_1234567890.docx
```

**响应**：
- 成功：返回DOCX文件流（application/vnd.openxmlformats-officedocument.wordprocessingml.document）
- 失败：返回JSON错误信息
  ```json
  {
    "ok": false,
    "msg": "该试卷暂无已完成的考试记录"
  }
  ```

**文件命名规则**：
- DOCX文件名：`{试卷名称}_成绩汇总_{时间戳}.docx`

## 前端调用示例

### JavaScript/TypeScript

```javascript
// 导出ZIP
async function exportGradesZip(paperId) {
  const url = `/mcq_public/grades/export_zip?paper_id=${encodeURIComponent(paperId)}`;
  
  try {
    const response = await fetch(url);
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.msg || '导出失败');
    }
    
    // 下载文件
    const blob = await response.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = `成绩报告_${Date.now()}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(downloadUrl);
  } catch (error) {
    console.error('导出ZIP失败:', error);
    alert(error.message);
  }
}

// 导出汇总DOCX
async function exportSummaryDocx(paperId) {
  const url = `/mcq_public/grades/export_summary_docx?paper_id=${encodeURIComponent(paperId)}`;
  
  try {
    const response = await fetch(url);
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.msg || '导出失败');
    }
    
    // 下载文件
    const blob = await response.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = `成绩汇总_${Date.now()}.docx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(downloadUrl);
  } catch (error) {
    console.error('导出汇总失败:', error);
    alert(error.message);
  }
}
```

### Vue 3 示例

```vue
<template>
  <div class="export-buttons">
    <button @click="handleExportZip" :disabled="loading">
      <i class="icon-download"></i>
      导出ZIP（所有学生报告）
    </button>
    <button @click="handleExportSummary" :disabled="loading">
      <i class="icon-table"></i>
      导出成绩汇总表
    </button>
  </div>
</template>

<script setup>
import { ref } from 'vue';

const props = defineProps({
  paperId: {
    type: String,
    required: true
  }
});

const loading = ref(false);

async function downloadFile(url, defaultFilename) {
  const response = await fetch(url);
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.msg || '导出失败');
  }
  
  const blob = await response.blob();
  const downloadUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = downloadUrl;
  a.download = defaultFilename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(downloadUrl);
}

async function handleExportZip() {
  loading.value = true;
  try {
    const url = `/mcq_public/grades/export_zip?paper_id=${encodeURIComponent(props.paperId)}`;
    await downloadFile(url, `成绩报告_${Date.now()}.zip`);
  } catch (error) {
    console.error('导出ZIP失败:', error);
    alert(error.message);
  } finally {
    loading.value = false;
  }
}

async function handleExportSummary() {
  loading.value = true;
  try {
    const url = `/mcq_public/grades/export_summary_docx?paper_id=${encodeURIComponent(props.paperId)}`;
    await downloadFile(url, `成绩汇总_${Date.now()}.docx`);
  } catch (error) {
    console.error('导出汇总失败:', error);
    alert(error.message);
  } finally {
    loading.value = false;
  }
}
</script>
```

## 后端实现细节

### 服务层函数

#### `export_paper_reports_zip(paper_id: str) -> Tuple[Optional[str], str]`

**功能**：导出指定试卷所有考生的成绩报告ZIP

**实现流程**：
1. 获取该试卷的所有已完成考试记录
2. 为每个考生生成独立的DOCX报告
3. 将所有报告打包成ZIP
4. 清理临时文件
5. 返回ZIP文件路径和文件名

**返回值**：
- 成功：`(ZIP文件路径, ZIP文件名)`
- 失败：`(None, "")`

#### `export_paper_summary_docx(paper_id: str) -> Tuple[Optional[str], str]`

**功能**：导出指定试卷所有考生的成绩汇总表

**实现流程**：
1. 获取该试卷的所有已完成考试记录
2. 创建DOCX文档
3. 生成汇总表格（学生ID + 每题答题情况 + 总分）
4. 添加统计信息（平均分、最高分、最低分）
5. 保存文件
6. 返回文件路径和文件名

**返回值**：
- 成功：`(DOCX文件路径, DOCX文件名)`
- 失败：`(None, "")`

### 数据存储

- **考试记录**：存储在 `./data/exam_attempts.json`
- **临时报告**：存储在 `./data/reports_temp/`（导出后自动清理）
- **ZIP文件**：存储在 `./data/reports_zip/`
- **汇总DOCX**：存储在 `./data/reports/`

## 注意事项

1. **依赖库**：需要安装 `python-docx` 库
   ```bash
   pip install python-docx
   ```

2. **文件清理**：
   - ZIP导出会自动清理临时DOCX文件
   - 建议定期清理 `./data/reports_zip/` 和 `./data/reports/` 目录

3. **性能考虑**：
   - 大量考生时，ZIP导出可能耗时较长
   - 建议在前端显示加载状态

4. **权限控制**：
   - 当前接口未添加权限验证
   - 建议在生产环境中添加教师/管理员权限验证

5. **错误处理**：
   - 如果试卷没有已完成的考试记录，返回404错误
   - 如果导出过程出错，返回500错误并记录日志

## 未来优化方向

1. **异步导出**：对于大量考生的情况，可以改为异步任务，避免请求超时
2. **自定义模板**：支持自定义DOCX模板样式
3. **Excel导出**：增加Excel格式的汇总表导出
4. **邮件发送**：支持直接将成绩报告发送到学生邮箱
5. **权限控制**：添加基于角色的访问控制（RBAC）
