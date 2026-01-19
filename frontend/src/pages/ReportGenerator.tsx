import { useState, useEffect } from 'react';
import { Button, Card, Typography, Space, message, Spin, Input } from 'antd';
import { fetchSectionsMeta, generateSection as generateSectionApi } from '../api/research';

type SectionItem = { id: string; title: string; desc?: string; default?: boolean; category?: string }


type GeneratedContent = { [key: string]: string };

export default function ReportGenerator() {
  const [selectedSections, setSelectedSections] = useState<string[]>([]);
  const [generated, setGenerated] = useState<GeneratedContent>({});
  const [loading, setLoading] = useState<{ [key: string]: boolean }>({});
  const [templateLoaded, setTemplateLoaded] = useState(false);
  const [jobId, setJobId] = useState('');
  const [metaSections, setMetaSections] = useState<SectionItem[]>([]);

  useEffect(() => {
    const init = async () => {
      try {
        const meta = await fetchSectionsMeta();
        const secs: SectionItem[] = meta.sections || [];
        setMetaSections(secs);
        const saved = localStorage.getItem('rws_report_template');
        if (saved) {
          const { selected, order } = JSON.parse(saved);
          const defaultIds = secs.filter((s) => s.default).map((s) => s.id);
          const ordered = (order || defaultIds).filter((id: string) => (selected || defaultIds).includes(id));
          setSelectedSections(ordered);
        } else {
          const defaults = secs.filter((s) => s.default).map((s) => s.id);
          setSelectedSections(defaults);
        }
      } catch {}
      setTemplateLoaded(true);
    };
    init();
  }, []);

  const generateOneSection = async (sectionId: string) => {
    if (!jobId) {
      message.error('请先输入Job ID');
      return;
    }
    setLoading(prev => ({ ...prev, [sectionId]: true }));
    try {
      const res = await generateSectionApi(jobId, sectionId);
      setGenerated(prev => ({ ...prev, [sectionId]: res.content }));
      message.success(`${sectionId} 生成成功`);
    } catch (error) {
      message.error(`${sectionId} 生成失败`);
    }
    setLoading(prev => ({ ...prev, [sectionId]: false }));
  };

  if (!templateLoaded) return <Spin />;

  return (
    <div>
      <Typography.Title level={3}>报告生成界面</Typography.Title>
      <Card>
        <Typography.Paragraph>选择模板后，可逐章节手动生成内容。</Typography.Paragraph>
        <Input
          placeholder="输入Job ID"
          value={jobId}
          onChange={e => setJobId(e.target.value)}
          style={{ marginBottom: 16 }}
        />
        <Space direction="vertical" style={{ width: '100%' }}>
          {selectedSections.map((id: string) => {
            const section = metaSections.find((s: SectionItem) => s.id === id);
            return (
              <Card key={id} title={section?.title || id} extra={
                <Button onClick={() => generateOneSection(id)} loading={loading[id]}>生成</Button>
              }>
                {generated[id] ? <div>{generated[id]}</div> : <Typography.Text type="secondary">未生成</Typography.Text>}
              </Card>
            );
          })}
        </Space>
      </Card>
    </div>
  );
}