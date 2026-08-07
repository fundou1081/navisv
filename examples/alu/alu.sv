// alu.sv — Simple 8-bit ALU (arithmetic logic unit)
// 经典 RTL 例子: counter, alu, fifo, uart
module alu (
    input  logic [7:0] a, b,
    input  logic [2:0] op,  // 3-bit opcode
    output logic [7:0] result,
    output logic        zero, carry, overflow
);
    logic [8:0] tmp;  // 9-bit for carry

    always_comb begin
        tmp = '0;
        case (op)
            3'b000: begin result = a + b;  tmp = {1'b0, a} + {1'b0, b}; end  // ADD
            3'b001: begin result = a - b;  tmp = {1'b0, a} - {1'b0, b}; end  // SUB
            3'b010:       result = a & b;                                       // AND
            3'b011:       result = a | b;                                       // OR
            3'b100:       result = a ^ b;                                       // XOR
            3'b101:       result = ~a;                                          // NOT
            3'b110:       result = a << b[2:0];                                 // SHL
            3'b111:       result = a >> b[2:0];                                 // SHR
        endcase

        zero     = (result == 8'd0);
        carry    = tmp[8];
        overflow = ((a[7] == b[7]) && (result[7] != a[7]));
    end
endmodule
