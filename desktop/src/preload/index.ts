import { contextBridge, ipcRenderer } from "electron"

import {
  IPC_CHANNELS,
  type AuthResult,
  type ApiRequestOptions,
  type ApiResponse,
  type BridgeCaptureResult,
  type BridgeResult,
  type FdeBridge,
  type LoginInput,
} from "../shared/contracts"

const bridge: FdeBridge = Object.freeze({
  auth: Object.freeze({
    login: (input: LoginInput): Promise<BridgeResult<AuthResult>> =>
      ipcRenderer.invoke(IPC_CHANNELS.authLogin, input),
    refresh: (): Promise<BridgeResult<AuthResult | null>> =>
      ipcRenderer.invoke(IPC_CHANNELS.authRefresh),
    changePassword: (
      accessToken: string,
      currentPassword: string,
      newPassword: string,
    ): Promise<BridgeResult<AuthResult>> =>
      ipcRenderer.invoke(
        IPC_CHANNELS.authChangePassword,
        accessToken,
        currentPassword,
        newPassword,
      ),
    logout: (): Promise<BridgeResult<null>> =>
      ipcRenderer.invoke(IPC_CHANNELS.authLogout),
  }),
  api: Object.freeze({
    request: <T>(
      path: string,
      options: ApiRequestOptions,
    ): Promise<BridgeResult<ApiResponse<T>>> =>
      ipcRenderer.invoke(IPC_CHANNELS.apiRequest, { path, ...options }),
  }),
  bridge: Object.freeze({
    capture: (): Promise<BridgeResult<BridgeCaptureResult>> =>
      ipcRenderer.invoke(IPC_CHANNELS.bridgeCapture),
  }),
  app: Object.freeze({
    version: () => ipcRenderer.invoke(IPC_CHANNELS.appVersion),
    setLcscEnabled: (enabled: boolean): Promise<void> => ipcRenderer.invoke(IPC_CHANNELS.appSetLcscEnabled, enabled),
    openLcscBrowser: (url: string): Promise<void> => ipcRenderer.invoke(IPC_CHANNELS.appOpenLcscBrowser, url),
    showLcscDownload: (filename: string): Promise<void> => ipcRenderer.invoke(IPC_CHANNELS.appShowLcscDownload, filename),
    copyLcscRunId: (id: string): Promise<void> => ipcRenderer.invoke(IPC_CHANNELS.appCopyLcscRunId, id),
    // CR-056（夜审 r6 设计稿 A′）：直连分片上传在途写计数面——把 renderer 直连
    // signed URL 的 PUT 计入 main 的 activeMutations，close-guard 才能拦下
    // 100MB 级上传中途的关窗（此前 4 处直连上传完全绕开计数）。
    uploadBegin: (label: string): Promise<void> => ipcRenderer.invoke(IPC_CHANNELS.appUploadBegin, label),
    uploadEnd: (label: string): Promise<void> => ipcRenderer.invoke(IPC_CHANNELS.appUploadEnd, label),
  }),
})

contextBridge.exposeInMainWorld("fde", bridge)
