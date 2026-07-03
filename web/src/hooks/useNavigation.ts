import { useState, useCallback, useMemo } from 'react';

export type View = 'start' | 'history' | 'chat';

/**
 * 导航状态管理 Hook
 * 支持三个视图：起始菜单、历史管理、聊天界面
 */
export function useNavigation(initialView: View = 'start') {
  const [currentView, setCurrentView] = useState<View>(initialView);
  const [chatParams, setChatParams] = useState<{
    conversationId?: string;
    branchId?: string;
  }>({});

  // 导航方法
  const toStart = useCallback(() => {
    setCurrentView('start');
  }, []);

  const toHistory = useCallback(() => {
    setCurrentView('history');
  }, []);

  const toChat = useCallback((params?: { conversationId?: string; branchId?: string }) => {
    setChatParams(params ?? {});
    setCurrentView('chat');
  }, []);

  // 导航对象（方便传递）
  const navigate = useMemo(() => ({
    toStart,
    toHistory,
    toChat,
  }), [toStart, toHistory, toChat]);

  // 便捷检查
  const isStart = currentView === 'start';
  const isHistory = currentView === 'history';
  const isChat = currentView === 'chat';

  return {
    // 当前视图
    currentView,
    // 聊天参数
    chatParams,
    // 导航方法
    navigate,
    // 便捷检查
    isStart,
    isHistory,
    isChat,
  };
}
