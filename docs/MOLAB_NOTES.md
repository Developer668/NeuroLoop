# Hosted notebook permission

The supplied implementation guide warns against treating molab compute as an unrestricted external web backend. NeuroLoop does not expose an inbound notebook service. Its worker initiates outbound calls to an approved CPU API.

Outbound polling is NOT a loophole: confirm with hackathon/provider staff that the entire workload and compute-to-app use are permitted. Set the provider-workload approval flag only after that confirmation. Use another approved runtime when necessary. Provider session timeouts require durable app state and notebook receipt storage; no permanent GPU availability is assumed.
