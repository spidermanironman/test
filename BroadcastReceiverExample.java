import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

/**
 * 广播接收器示例
 * 演示如何在广播处理中使用线程状态检查
 */
public class BroadcastReceiverExample extends BroadcastReceiver {
    private static final String TAG = "BroadcastReceiverExample";
    
    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        String threadName = Thread.currentThread().getName();
        
        // 注册当前线程
        BroadcastThreadStatusChecker.registerBroadcastThread(
            threadName, 
            action != null ? action : "unknown"
        );
        
        Log.d(TAG, "收到广播: " + action + ", 处理线程: " + threadName);
        
        // 执行广播处理逻辑
        processBroadcast(context, intent);
        
        // 处理完成后检查状态
        BroadcastThreadStatusChecker.updateThreadStatus(
            threadName, 
            BroadcastThreadStatusChecker.ThreadState.NORMAL
        );
    }
    
    private void processBroadcast(Context context, Intent intent) {
        // 模拟广播处理逻辑
        try {
            // 执行一些操作
            Thread.sleep(100); // 模拟处理时间
            
            // 在处理过程中可以检查线程状态
            boolean allNormal = BroadcastThreadStatusChecker.checkAllBroadcastThreadsNormal();
            Log.d(TAG, "广播处理中，所有线程状态正常: " + allNormal);
            
        } catch (InterruptedException e) {
            Log.e(TAG, "广播处理被中断", e);
            Thread.currentThread().interrupt();
        }
    }
}
