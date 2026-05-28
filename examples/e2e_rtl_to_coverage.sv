// examples/e2e_rtl_to_coverage.sv
// 端到端示例：RTL hierarchy → Constraint → Coverage 完整链路
//
// 场景：一个简单的 AXI-like 数据通路
//   - 有随机化约束（控制数据范围、条件约束）
//   - 有 covergroup 覆盖约束空间
//   - 需要验证：约束产生的值空间是否被覆盖组完整覆盖

module e2e_coverage_demo (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  data_in,
    output reg  [7:0]  data_out,
    output reg         overflow
);

    // ============================================================
    // 1. 数据通路寄存器
    // ============================================================
    reg [7:0] pipeline_data;
    reg       pipeline_valid;
    reg [1:0] mode;

    // 流水线寄存器
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pipeline_data <= 8'h00;
            pipeline_valid <= 1'b0;
            mode <= 2'b00;
        end else begin
            pipeline_data <= data_in;
            pipeline_valid <= 1'b1;
            mode <= data_in[1:0];
        end
    end

    // 输出逻辑
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            data_out <= 8'h00;
            overflow <= 1'b0;
        end else begin
            case (mode)
                2'b00: data_out <= pipeline_data;
                2'b01: data_out <= pipeline_data + 1;
                2'b10: data_out <= pipeline_data - 1;
                2'b11: data_out <= ~pipeline_data;
            endcase
            overflow <= (pipeline_data > 8'hF0) && (mode == 2'b01);
        end
    end

    // ============================================================
    // 2. 约束 (模拟 class 内的 randomize 约束)
    // ============================================================
    // 约束类：描述 data_in 的随机化空间
    class data_constraint;
        rand bit [7:0] data;
        rand bit [1:0] op_mode;

        // 基本约束：data 在 0-200 范围
        constraint c_data_range {
            data inside {[0:200]};
        }

        // 条件约束：当 mode==3 时，data 必须 < 100
        constraint c_mode3_limit {
            if (op_mode == 2'b11)
                data < 8'd100;
        }

        // 边界约束：data 不能为 0
        constraint c_no_zero {
            data != 8'h00;
        }
    endclass

    // ============================================================
    // 3. CoverGroup (覆盖约束空间)
    // ============================================================
    covergroup cg_data @(posedge clk);
        // 覆盖 data_in 的值空间
        cp_data: coverpoint data_in {
            bins low       = {[1:50]};
            bins mid       = {[51:100]};
            bins high      = {[101:200]};
            bins extreme   = {[201:255]};
            bins zero_val  = {0};
        }

        // 覆盖 mode 分布
        cp_mode: coverpoint mode {
            bins m0 = {2'b00};
            bins m1 = {2'b01};
            bins m2 = {2'b10};
            bins m3 = {2'b11};
        }

        // 覆盖 overflow 条件
        cp_overflow: coverpoint overflow {
            bins no_ovf  = {0};
            bins ovf     = {1};
        }

        // 交叉覆盖：data 范围 x mode
        cx_data_mode: cross cp_data, cp_mode;
    endgroup

    // 实例化 covergroup
    cg_data cov_inst = new();

endmodule
