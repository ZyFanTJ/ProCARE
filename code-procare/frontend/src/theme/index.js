import { theme } from 'antd';
export const getTheme = (mode) => {
    const isDark = mode === 'dark';
    // Professional Research Palette
    const colors = {
        primary: '#6366f1', // Indigo 500
        primaryDark: '#4f46e5', // Indigo 600
        success: '#10b981', // Emerald 500
        warning: '#f59e0b', // Amber 500
        error: '#ef4444', // Red 500
        info: '#3b82f6', // Blue 500
        bgBase: isDark ? '#0f172a' : '#f8fafc', // Slate 900 / Slate 50
        bgContainer: isDark ? '#1e293b' : '#ffffff', // Slate 800 / White
        bgElevated: isDark ? '#1e293b' : '#ffffff',
        textBase: isDark ? '#f1f5f9' : '#0f172a', // Slate 100 / Slate 900
        textSecondary: isDark ? '#94a3b8' : '#64748b', // Slate 400 / Slate 500
        border: isDark ? '#334155' : '#e2e8f0', // Slate 700 / Slate 200
    };
    return {
        algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
            colorPrimary: colors.primary,
            colorSuccess: colors.success,
            colorWarning: colors.warning,
            colorError: colors.error,
            colorInfo: colors.info,
            colorBgBase: colors.bgBase,
            colorBgContainer: colors.bgContainer,
            colorBgElevated: colors.bgElevated,
            colorTextBase: colors.textBase,
            colorTextSecondary: colors.textSecondary,
            colorBorder: colors.border,
            colorBorderSecondary: isDark ? '#1e293b' : '#f1f5f9',
            fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
            fontSize: 14,
            borderRadius: 6,
            wireframe: false,
        },
        components: {
            Layout: {
                bodyBg: colors.bgBase,
                headerBg: colors.bgContainer,
                siderBg: colors.bgContainer,
                triggerBg: colors.bgContainer,
            },
            Menu: {
                itemBg: 'transparent',
                subMenuItemBg: 'transparent',
                activeBarBorderWidth: 0,
                itemSelectedColor: colors.primary,
                itemSelectedBg: isDark ? 'rgba(99, 102, 241, 0.15)' : 'rgba(99, 102, 241, 0.1)',
                itemHoverBg: isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.03)',
                itemColor: colors.textSecondary,
                itemHoverColor: colors.textBase,
            },
            Card: {
                colorBgContainer: colors.bgContainer,
                headerBg: 'transparent',
                boxShadow: isDark
                    ? '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)'
                    : '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03)',
                actionsBg: 'transparent',
            },
            Button: {
                controlHeight: 36,
                primaryShadow: 'none',
                defaultShadow: 'none',
            },
            Input: {
                controlHeight: 36,
                colorBgContainer: isDark ? '#0f172a' : '#ffffff',
                activeBorderColor: colors.primary,
                hoverBorderColor: colors.primary,
            },
            Table: {
                headerBg: isDark ? '#1e293b' : '#f8fafc',
                headerColor: colors.textSecondary,
                borderColor: colors.border,
            },
            Tabs: {
                itemColor: colors.textSecondary,
                itemSelectedColor: colors.primary,
                itemHoverColor: colors.primary,
            }
        },
    };
};
