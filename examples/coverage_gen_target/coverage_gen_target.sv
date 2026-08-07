// examples/coverage_gen_target.sv
// 目标 RTL：带 FSM + 数据通路的模块
// navisv 将自动为它生成 covergroup

module coverage_gen_target (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  data_in,
    input  wire [1:0]  cmd,
    input  wire        valid,
    output reg  [7:0]  data_out,
    output reg         ready,
    output reg         error
);

    // ============================================================
    // FSM
    // ============================================================
    typedef enum logic [2:0] {
        IDLE     = 3'b000,
        FETCH    = 3'b001,
        DECODE   = 3'b010,
        EXECUTE  = 3'b011,
        WRITEBACK= 3'b100,
        ERROR    = 3'b101
    } state_t;

    state_t state, next_state;

    // FSM 状态转移
    always_comb begin
        next_state = IDLE;
        case (state)
            IDLE: begin
                if (valid)
                    next_state = FETCH;
                else
                    next_state = IDLE;
            end
            FETCH: begin
                next_state = DECODE;
            end
            DECODE: begin
                case (cmd)
                    2'b00: next_state = EXECUTE;
                    2'b01: next_state = EXECUTE;
                    2'b10: next_state = WRITEBACK;
                    2'b11: next_state = ERROR;
                endcase
            end
            EXECUTE: begin
                if (data_in > 8'hF0)
                    next_state = ERROR;
                else
                    next_state = WRITEBACK;
            end
            WRITEBACK: begin
                next_state = IDLE;
            end
            ERROR: begin
                if (!rst_n)
                    next_state = IDLE;
                else
                    next_state = ERROR;
            end
            default: next_state = IDLE;
        endcase
    end

    // FSM 状态寄存器
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            state <= IDLE;
        else
            state <= next_state;
    end

    // ============================================================
    // 数据通路
    // ============================================================
    reg [7:0] operand_a;
    reg [7:0] operand_b;
    reg [7:0] alu_result;

    // 操作数寄存器
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            operand_a <= 8'h00;
            operand_b <= 8'h00;
        end else if (state == FETCH) begin
            operand_a <= data_in;
            operand_b <= data_in + 8'h01;
        end
    end

    // ALU
    always @(*) begin
        case (cmd)
            2'b00: alu_result = operand_a + operand_b;
            2'b01: alu_result = operand_a - operand_b;
            2'b10: alu_result = operand_a & operand_b;
            2'b11: alu_result = operand_a | operand_b;
        endcase
    end

    // 输出逻辑
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            data_out <= 8'h00;
            ready <= 1'b0;
            error <= 1'b0;
        end else begin
            case (state)
                WRITEBACK: begin
                    data_out <= alu_result;
                    ready <= 1'b1;
                    error <= 1'b0;
                end
                ERROR: begin
                    data_out <= 8'hFF;
                    ready <= 1'b0;
                    error <= 1'b1;
                end
                default: begin
                    ready <= 1'b0;
                    error <= 1'b0;
                end
            endcase
        end
    end

endmodule
