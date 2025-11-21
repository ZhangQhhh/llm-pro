# 数据趋势分析 API 文档

## 概述

数据趋势分析接口用于接收 Java Spring Boot 后端解析的 Excel 统计数据，调用 LLM 生成趋势分析摘要，供前端下载为 Word 文档。

## 接口信息

- **路径**: `POST /api/data/trend_summary`
- **认证**: 需要 Bearer Token
- **Content-Type**: `application/json`

## 请求参数

### 请求体格式

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "totalCount": 1000,
    "entryCount": 600,
    "exitCount": 400,
    "maleCount": 550, 
    "femaleCount": 450,
    "transportationToolStats": {
      "SL8103": 150,
      "CA1234": 200
    },
    "countryRegionStats": {
      "泰国": 300,
      "中国": 400
    },
    "transportationModeStats": {
      "1": 500,
      "2": 500
    },
    "personCategoryStats": {
      "26": 800
    },
    "ethnicityStats": {
      "汉族": 700
    }
  },
  "model_id": "qwen2025",
  "thinking": false,
  "stream": false
}
```

### 参数说明

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| data | Object | 是 | - | 统计数据对象 |
| data.totalCount | Integer | 是 | - | 总人数 |
| data.entryCount | Integer | 否 | 0 | 入境人数 |
| data.exitCount | Integer | 否 | 0 | 出境人数 |
| data.maleCount | Integer | 否 | 0 | 男性人数 |
| data.femaleCount | Integer | 否 | 0 | 女性人数 |
| data.transportationToolStats | Object | 否 | {} | 交通工具统计（航班号/车次 → 人数） |
| data.countryRegionStats | Object | 否 | {} | 国家/地区统计（国家名 → 人数） |
| data.transportationModeStats | Object | 否 | {} | 交通方式统计（1=航空, 2=陆路, 3=水路, 4=铁路） |
| data.personCategoryStats | Object | 否 | {} | 人员类别统计（类别代码 → 人数） |
| data.ethnicityStats | Object | 否 | {} | 民族统计（民族名 → 人数） |
| model_id | String | 否 | Settings.DEFAULT_LLM_ID | 使用的 LLM 模型 ID |
| thinking | Boolean | 否 | false | 是否启用思考模式 |
| stream | Boolean | 否 | true | 是否使用 SSE 流式输出 |

### 交通方式代码映射

- `"1"`: 航空
- `"2"`: 陆路
- `"3"`: 水路
- `"4"`: 铁路

### 人员类别代码映射（示例）

- `"26"`: 普通旅客
- `"01"`: 外交人员
- `"02"`: 公务人员
- `"03"`: 商务人员
- `"04"`: 劳务人员
- `"05"`: 留学人员

## 响应格式

### 流式输出 (stream=true)

**Content-Type**: `text/event-stream`

```
data: THINK:分析数据中...\n\n
data: THINK:发现主要趋势...\n\n
data: CONTENT:本次统计数据显示...\n\n
data: CONTENT:入境人数占比60%...\n\n
data: DONE:\n\n
```

### 同步输出 (stream=false)

**Content-Type**: `application/json`

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "summary": "本次统计数据显示，总计1,000人次出入境，其中入境600人(60.0%)，出境400人(40.0%)，入境人数明显高于出境。性别分布较为均衡，男性550人(55.0%)，女性450人(45.0%)。交通工具方面，主要集中在CA1234航班200人(20.0%)、SL8103航班150人(15.0%)。国家/地区分布显示，中国400人(40.0%)、泰国300人(30.0%)为主要来源。交通方式均衡，航空500人(50.0%)、陆路500人(50.0%)。人员类别以普通旅客为主800人(80.0%)，民族构成以汉族为主700人(70.0%)。",
    "model_id": "qwen2025"
  }
}
```

### 错误响应

```json
{
  "code": 400,
  "message": "数据验证失败：totalCount 必须是非负数字",
  "data": null
}
```

## 使用示例

### Python 示例（流式）

```python
import requests
import json

url = "http://53.3.1.2/llm/api/data/trend_summary"
headers = {
    "Authorization": "Bearer your_token_here",
    "Content-Type": "application/json"
}

data = {
    "data": {
        "totalCount": 1000,
        "entryCount": 600,
        "exitCount": 400,
        "maleCount": 550,
        "femaleCount": 450,
        "transportationToolStats": {
            "SL8103": 150,
            "CA1234": 200
        },
        "countryRegionStats": {
            "泰国": 300,
            "中国": 400
        },
        "transportationModeStats": {
            "1": 500,
            "2": 500
        },
        "personCategoryStats": {
            "26": 800
        },
        "ethnicityStats": {
            "汉族": 700
        }
    },
    "model_id": "qwen2025",
    "thinking": False,
    "stream": True
}

response = requests.post(url, headers=headers, json=data, stream=True)

for line in response.iter_lines():
    if line:
        line_str = line.decode('utf-8')
        if line_str.startswith('data: '):
            content = line_str[6:]  # 去掉 "data: " 前缀
            print(content)
```

### Python 示例（同步）

```python
import requests
import json

url = "http://53.3.1.2/llm/api/data/trend_summary"
headers = {
    "Authorization": "Bearer your_token_here",
    "Content-Type": "application/json"
}

data = {
    "data": {
        "totalCount": 1000,
        "entryCount": 600,
        "exitCount": 400,
        # ... 其他字段
    },
    "model_id": "qwen2025",
    "thinking": False,
    "stream": False
}

response = requests.post(url, headers=headers, json=data)
result = response.json()

if result["code"] == 200:
    summary = result["data"]["summary"]
    print(f"分析摘要: {summary}")
else:
    print(f"错误: {result['message']}")
```

### Java Spring Boot 示例

```java
import org.springframework.http.*;
import org.springframework.web.client.RestTemplate;
import java.util.HashMap;
import java.util.Map;

public class DataTrendAnalysisClient {
    
    public String analyzeTrend(Map<String, Object> statsData, String token) {
        RestTemplate restTemplate = new RestTemplate();
        
        String url = "http://53.3.1.2/llm/api/data/trend_summary";
        
        // 构建请求头
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setBearerAuth(token);
        
        // 构建请求体
        Map<String, Object> requestBody = new HashMap<>();
        requestBody.put("data", statsData);
        requestBody.put("model_id", "qwen2025");
        requestBody.put("thinking", false);
        requestBody.put("stream", false);  // 同步模式
        
        HttpEntity<Map<String, Object>> request = new HttpEntity<>(requestBody, headers);
        
        // 发送请求
        ResponseEntity<Map> response = restTemplate.postForEntity(url, request, Map.class);
        
        if (response.getStatusCode() == HttpStatus.OK) {
            Map<String, Object> body = response.getBody();
            Map<String, Object> data = (Map<String, Object>) body.get("data");
            return (String) data.get("summary");
        } else {
            throw new RuntimeException("分析失败: " + response.getBody());
        }
    }
}
```

## 数据验证规则

1. **必需字段**: `totalCount` 必须提供
2. **数值范围**: 所有数值必须 >= 0
3. **逻辑校验**: 
   - 出入境人数之和不应超过总人数的 110%（允许10%误差）
   - 男女人数之和不应超过总人数的 110%（允许10%误差）

## 分析摘要特点

LLM 生成的趋势分析摘要将包含：

1. **出入境对比**: 入境/出境比例，是否平衡
2. **性别比例**: 男女比例是否均衡
3. **交通工具集中度**: 是否集中在某几个航班/车次
4. **国家/地区主力**: 主要来源国或目的地
5. **人员类别亮点**: 主要人员类型
6. **民族分布特点**: 如果有显著特征

摘要长度控制在 **150字以内**，适合直接写入 Word 文档。

## 错误码说明

| 错误码 | 说明 |
|--------|------|
| 400 | 请求参数错误或数据验证失败 |
| 401 | 未提供认证令牌或令牌无效 |
| 500 | 服务器内部错误 |

## 注意事项

1. **缺失数据处理**: 对于未提供的统计项，分析中会说明"该项数据未提供"
2. **数据准确性**: 引用数据时使用原始数字和百分比
3. **流式输出**: 推荐使用流式输出，可实时显示分析进度
4. **思考模式**: 启用思考模式会输出 LLM 的分析过程，但会增加响应时间
5. **模型选择**: 
   - 推荐使用 `qwen2025` 或 `qwen3-32b` 获得快速响应
   - 使用 `deepseek-r1` 会有更深入的分析，但响应时间较长

## 性能参考

- **qwen2025**: 约 2-5 秒
- **qwen3-32b**: 约 3-8 秒
- **deepseek-r1**: 约 10-30 秒（含推理过程）

## 集成流程

```
Excel 文件 
  ↓
Java Spring Boot 解析
  ↓
调用 /api/data/trend_summary
  ↓
接收分析摘要
  ↓
写入 Word 文档
  ↓
返回给前端下载
```
